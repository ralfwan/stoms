from __future__ import annotations

import argparse
import contextlib
import html
import io
import json
import os
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .atomsledger import (
    AggregationNotFoundError,
    AggregationValidationError,
    AtomsLedger,
    RecordNotFoundError,
    StrictSelectionError,
)
from .atomsledger.serialization import (
    json_dumps,
    method_to_dict,
    provenance_to_dict,
    structure_source_to_dict,
    to_plain,
)


def _json(value: Any) -> str:
    return json.dumps(
        to_plain(value), sort_keys=True, indent=2, ensure_ascii=True
    )


def _key(value: Any) -> str:
    return json_dumps(value)


def _html_json(value: Any) -> str:
    return html.escape(_json(value))


def _html_tree(
    value: Any, label: str, *, depth: int = 0, full_collapse: bool = False
) -> str:
    value = to_plain(value)
    if isinstance(value, dict):
        if not value:
            return f"<details><summary>{_html_label(label)}: {{}}</summary></details>"
        children = "".join(
            _html_tree(
                item,
                str(key),
                depth=depth + 1,
                full_collapse=full_collapse,
            )
            for key, item in value.items()
        )
    elif isinstance(value, list):
        if not value:
            return f"<details><summary>{_html_label(label)}: []</summary></details>"
        children = "".join(
            _html_tree(
                item,
                f"[{index}]",
                depth=depth + 1,
                full_collapse=full_collapse,
            )
            for index, item in enumerate(value)
        )
    else:
        return (
            f'<div class="value"><span class="label">'
            f"{_html_label(label)}:</span> <code>"
            f"{html.escape(json.dumps(value, ensure_ascii=True))}</code></div>"
        )
    open_attribute = "" if full_collapse or depth < 2 else " open"
    return (
        f"<details{open_attribute}><summary>{_html_label(label)}</summary>"
        f"{children}</details>"
    )


def _html_label(value: str) -> str:
    return html.escape(value)


def _iteration_label(tags: Sequence[str]) -> str:
    iterations = [
        tag.removeprefix("iteration:")
        for tag in tags
        if tag.startswith("iteration:")
    ]
    return (
        f"iteration:{iterations[0]}"
        if len(iterations) == 1 and iterations[0]
        else "-"
    )


def _print_list(ledger: AtomsLedger) -> None:
    summaries = sorted(
        ledger.list_aggregations(),
        key=lambda item: (item.created_at, item.id),
        reverse=True,
    )
    if not summaries:
        print("No aggregations.")
        return
    for index, summary in enumerate(summaries):
        if index:
            print()
        print(f"ID: {summary.id}")
        print(f"Name: {summary.name}")
        print(f"Members: {summary.member_count}")
        print(f"Created: {summary.created_at.isoformat()}")
        print(f"Source stored query: {summary.source_stored_query_id or '-'}")
        print(f"Description: {summary.description or '-'}")


def _print_details(title: str, values: dict[str, tuple[str, Any]]) -> None:
    print(f"{title}:")
    for key, value in values.values():
        print(f"  {key}:")
        print(_json(value))


def _print_show(
    ledger: AtomsLedger,
    aggregation_id: str,
    details: str | None = None,
    structure_id: str | None = None,
) -> None:
    aggregation = ledger.get_aggregation(aggregation_id)
    print(f"Aggregation: {aggregation.name} ({aggregation.id})")
    print(f"Members: {len(aggregation.members)}")
    if aggregation.description:
        print(f"Description: {aggregation.description}")

    sources: dict[str, tuple[str, Any]] = {}
    methods: dict[str, tuple[str, Any]] = {}
    structure_provenance: dict[str, tuple[str, Any]] = {}
    evaluation_provenance: dict[str, tuple[str, Any]] = {}
    rows: list[tuple[Any, Any, Any, str, str | None, str | None]] = []
    detail_member = aggregation.members[0] if aggregation.members else None
    if structure_id is not None:
        detail_member = next(
            (
                member
                for member in aggregation.members
                if member.structure_id == structure_id
            ),
            None,
        )
        if detail_member is None:
            raise AggregationValidationError(
                f"Structure is not a member of aggregation: {structure_id}"
            )
    for member in aggregation.members:
        structure = ledger.repository.get_structure(member.structure_id)
        include_details = details is not None and member is detail_member
        source = structure_source_to_dict(structure.source_spec)
        source_key = _key(source)
        if include_details and details in ("source", "all"):
            sources.setdefault(source_key, (f"S{len(sources)}", source))
        structure_prov = provenance_to_dict(structure.provenance)
        structure_prov["effective_tags"] = list(structure.effective_tags)
        structure_prov_key = _key(structure_prov)
        if include_details and details in ("structure-provenance", "all"):
            structure_provenance.setdefault(
                structure_prov_key,
                (f"SP{len(structure_provenance)}", structure_prov),
            )
        evaluation = None
        method_key = evaluation_prov_key = None
        method_label = None
        if member.evaluation_id is not None:
            evaluation = ledger.repository.get_evaluation(member.evaluation_id)
            method = method_to_dict(evaluation.method)
            method_key = _key(method)
            method_label = (
                f"{evaluation.method.name}/"
                f"{evaluation.method.method_identifier}"
            )
            if include_details and details in ("method", "all"):
                methods.setdefault(method_key, (f"M{len(methods)}", method))
            evaluation_prov = provenance_to_dict(evaluation.provenance)
            evaluation_prov["effective_tags"] = list(evaluation.effective_tags)
            evaluation_prov_key = _key(evaluation_prov)
            if include_details and details in ("evaluation-provenance", "all"):
                evaluation_provenance.setdefault(
                    evaluation_prov_key,
                    (f"EP{len(evaluation_provenance)}", evaluation_prov),
                )
        rows.append(
            (
                member,
                structure,
                evaluation,
                "/".join(
                    part
                    for part in (
                        structure.source_spec.name,
                        structure.source_spec.tool,
                        structure.source_spec.kind,
                    )
                    if part
                ),
                method_label,
                evaluation_prov_key,
            )
        )

    print("Members:")
    for member, structure, evaluation, source_label, method_label, _ in rows:
        properties = (
            ", ".join(
                f"{name} [{evaluation.units.get(name, '-')}]"
                for name in sorted(evaluation.properties)
            )
            if evaluation is not None
            else "-"
        ) or "-"
        formula = structure.atoms.get_chemical_formula()
        iteration_label = _iteration_label(structure.effective_tags)
        print(
            f"  {member.ordinal}: structure={structure.id} formula={formula} "
            f"atoms={len(structure.atoms)} source={source_label} "
            f"iteration={iteration_label} "
            f"method={method_label or '-'} evaluation={evaluation.id if evaluation else '-'} "
            f"properties={properties}"
        )
    if details in ("source", "all"):
        _print_details("Structure sources", sources)
    if details in ("method", "all"):
        _print_details("Methods", methods)
    if details in ("structure-provenance", "all"):
        _print_details("Structure provenance", structure_provenance)
    if details in ("evaluation-provenance", "all"):
        _print_details("Evaluation provenance", evaluation_provenance)


def _print_html(
    ledger: AtomsLedger, aggregation_id: str, *, full_collapse: bool = False
) -> None:
    aggregation = ledger.get_aggregation(aggregation_id)
    members: list[tuple[Any, Any, Any, str, str | None]] = []
    for member in aggregation.members:
        structure = ledger.repository.get_structure(member.structure_id)
        evaluation = (
            ledger.repository.get_evaluation(member.evaluation_id)
            if member.evaluation_id is not None
            else None
        )
        source_label = "/".join(
            part
            for part in (
                structure.source_spec.name,
                structure.source_spec.tool,
                structure.source_spec.kind,
            )
            if part
        )
        method_label = (
            f"{evaluation.method.name}/{evaluation.method.method_identifier}"
            if evaluation is not None
            else None
        )
        members.append(
            (member, structure, evaluation, source_label, method_label)
        )

    print("<!doctype html>")
    print('<html lang="en"><head><meta charset="utf-8">')
    print(f"<title>STOMS aggregation: {_html_label(aggregation.name)}</title>")
    print(
        "<style>body{font-family:system-ui,sans-serif;line-height:1.4;"
        "max-width:1100px;margin:2rem auto;padding:0 1rem}"
        "code,pre{font-family:ui-monospace,monospace}"
        "pre{background:#f5f5f5;padding:1rem;overflow:auto}"
        "summary{cursor:pointer;padding:.5rem 0}"
        ".member{border-top:1px solid #ccc;padding:.25rem 0}"
        ".label{color:#555}</style></head><body>"
    )
    print(f"<h1>{_html_label(aggregation.name)}</h1>")
    print("<details><summary>Aggregation details</summary>")
    print(
        f'<p><span class="label">Aggregation:</span> '
        f"<code>{_html_label(aggregation.id)}</code><br>"
        f'<span class="label">Members:</span> {len(members)}</p>'
    )
    if aggregation.description:
        print(f"<p>{_html_label(aggregation.description)}</p>")
    print("</details>")
    print("<h2>Members</h2>")
    for member, structure, evaluation, source_label, method_label in members:
        formula = structure.atoms.get_chemical_formula()
        properties = (
            ", ".join(
                f"{name} [{evaluation.units.get(name, '-')}]"
                for name in sorted(evaluation.properties)
            )
            if evaluation is not None
            else "-"
        ) or "-"
        summary = (
            f"{member.ordinal}: {structure.id} | {formula} | "
            f"{source_label} | {_iteration_label(structure.effective_tags)} | "
            f"{method_label or '-'} | {properties}"
        )
        print('<div class="member">')
        print(f"<details><summary>{_html_label(summary)}</summary>")
        print(f"<p>Structure ID: <code>{structure.id}</code></p>")
        print(f"<p>Source: {_html_label(source_label)}</p>")
        print(
            _html_tree(
                structure_source_to_dict(structure.source_spec),
                "Structure source specification",
                full_collapse=full_collapse,
            )
        )
        structure_provenance = provenance_to_dict(structure.provenance)
        structure_provenance["effective_tags"] = list(structure.effective_tags)
        print(
            _html_tree(
                structure_provenance,
                "Structure provenance",
                full_collapse=full_collapse,
            )
        )
        if evaluation is None:
            print("<p>Evaluation: -</p>")
        else:
            print(
                f"<p>Evaluation ID: <code>{evaluation.id}</code></p>"
                f"<p>Method: {_html_label(method_label or '-')}</p>"
            )
            print(
                _html_tree(
                    method_to_dict(evaluation.method),
                    "Method specification",
                    full_collapse=full_collapse,
                )
            )
            evaluation_provenance = provenance_to_dict(evaluation.provenance)
            evaluation_provenance["effective_tags"] = list(
                evaluation.effective_tags
            )
            print(
                _html_tree(
                    evaluation_provenance,
                    "Evaluation provenance",
                    full_collapse=full_collapse,
                )
            )
        print("</details></div>")
    print("</body></html>")


def _html_document(
    ledger: AtomsLedger, aggregation_id: str, *, full_collapse: bool = False
) -> str:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        _print_html(ledger, aggregation_id, full_collapse=full_collapse)
    document = output.getvalue()
    return document[
        document.index("<body>") + len("<body>") : document.index("</body>")
    ]


def _print_report(ledger: AtomsLedger, *, full_collapse: bool = False) -> None:
    summaries = sorted(
        ledger.list_aggregations(),
        key=lambda item: (item.created_at, item.id),
        reverse=True,
    )
    print("<!doctype html>")
    print('<html lang="en"><head><meta charset="utf-8">')
    print("<title>STOMS aggregation report</title>")
    print(
        "<style>body{font-family:system-ui,sans-serif;line-height:1.4;"
        "max-width:1100px;margin:2rem auto;padding:0 1rem}"
        "code,pre{font-family:ui-monospace,monospace}"
        "pre{background:#f5f5f5;padding:1rem;overflow:auto}"
        "summary{cursor:pointer;padding:.5rem 0}"
        ".member{border-top:1px solid #ccc;padding:.25rem 0}"
        ".label{color:#555}.aggregation{border-top:2px solid #888;"
        "margin-top:2rem;padding-top:1rem}</style></head><body>"
    )
    print('<h1 id="top">STOMS aggregations</h1>')
    if not summaries:
        print("<p>No aggregations.</p></body></html>")
        return
    print("<h2>Index</h2><ul>")
    for summary in summaries:
        print(
            f'<li><a href="#{_html_label(summary.id)}">'
            f"{_html_label(summary.name)}</a> "
            f"({summary.member_count} members, "
            f"{_html_label(summary.id)})</li>"
        )
    print("</ul>")
    for summary in summaries:
        print(f'<section class="aggregation" id="{_html_label(summary.id)}">')
        print(_html_document(ledger, summary.id, full_collapse=full_collapse))
        print('<p><a href="#top">Back to index</a></p></section>')
    print("</body></html>")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stoms",
        description="Inspect immutable STOMS aggregations.",
        epilog=(
            "Examples:\n"
            "  stoms --ledger project.ledger aggregations list\n"
            "  stoms --ledger project.ledger aggregations show agg_...\n"
            "  stoms --ledger project.ledger serve --open\n"
            "  stoms --ledger project.ledger aggregations report > report.html\n"
            "  stoms --ledger project.ledger aggregations to-extxyz agg_... training.extxyz\n"
            "\n"
            "Report options:\n"
            "  --full-collapse  Collapse every nested detail block in the report\n"
            "\n"
            "extxyz export options:\n"
            "  --energy-label LABEL       Write energy values under LABEL\n"
            "  --forces-label LABEL       Write force values under LABEL\n"
            "  --node-energy-label LABEL  Write per-atom energies under LABEL\n"
            "  --include-node-energy      Include per-atom energies"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ledger", required=True, type=Path)
    commands = parser.add_subparsers(
        dest="command", required=True, title="commands"
    )
    serve = commands.add_parser(
        "serve",
        help="Browse the ledger in a local web homepage",
        description=(
            "Serve a read-only browser homepage for the ledger on the local "
            "machine. Stop it with Ctrl+C."
        ),
    )
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to bind (default: 127.0.0.1, local only)",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to listen on; 0 picks a free port (default: 8765)",
    )
    serve.add_argument(
        "--open",
        dest="open_browser",
        action="store_true",
        help="Open the homepage in the default browser",
    )
    aggregations = commands.add_parser(
        "aggregations",
        help="Inspect immutable aggregations",
        description="Inspect immutable aggregations in a ledger.",
    )
    aggregation_commands = aggregations.add_subparsers(
        dest="aggregation_command", required=True, title="aggregation commands"
    )
    aggregation_commands.add_parser(
        "list",
        help="List aggregations, newest first",
        description="List aggregations, newest first.",
    )
    show = aggregation_commands.add_parser(
        "show",
        help="Show one aggregation by its full ID",
        description="Show one immutable aggregation by its full ID.",
    )
    show.add_argument("aggregation_id")
    show.add_argument(
        "--details",
        choices=(
            "source",
            "method",
            "structure-provenance",
            "evaluation-provenance",
            "all",
        ),
        help="Also print one grouped detail section (or all sections)",
    )
    show.add_argument(
        "--structure",
        dest="structure_id",
        help="Limit details to this member; defaults to the first member",
    )
    show.add_argument(
        "--format",
        choices=("text", "html"),
        default="text",
        help="Output format (default: text)",
    )
    show.add_argument(
        "--full-collapse",
        action="store_true",
        help="With HTML output, collapse every nested detail block",
    )
    report = aggregation_commands.add_parser(
        "report",
        help="Create a single HTML report with links to all aggregations",
        description="Create a single-file HTML report of all aggregations.",
    )
    report.add_argument(
        "--full-collapse",
        action="store_true",
        help="Collapse every nested detail block in the report",
    )
    to_extxyz = aggregation_commands.add_parser(
        "to-extxyz",
        help="Export one aggregation to extxyz",
        description=(
            "Export an aggregation's immutable member order and attached "
            "evaluations to extxyz."
        ),
    )
    to_extxyz.add_argument("aggregation_id", help="Full aggregation ID")
    to_extxyz.add_argument("destination", type=Path, help="Output extxyz path")
    to_extxyz.add_argument(
        "--energy-label",
        default="REF_energy",
        help="extxyz energy property name",
    )
    to_extxyz.add_argument(
        "--forces-label",
        default="REF_forces",
        help="extxyz forces property name",
    )
    to_extxyz.add_argument(
        "--node-energy-label",
        default="REF_node_energy",
        help="extxyz per-atom energy property name",
    )
    to_extxyz.add_argument(
        "--include-node-energy",
        action="store_true",
        help="Include per-atom energies when available",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    path = args.ledger
    if not path.is_file() or not os.access(path, os.R_OK):
        print(
            f"error: ledger is not a readable regular file: {path}",
            file=sys.stderr,
        )
        return 1
    if args.command == "serve":
        from .web import serve

        try:
            serve(
                path,
                host=args.host,
                port=args.port,
                open_browser=args.open_browser,
            )
        except sqlite3.DatabaseError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        except OSError as error:
            print(f"error: cannot start server: {error}", file=sys.stderr)
            return 1
        return 0
    try:
        ledger = AtomsLedger(path)
        if args.aggregation_command == "list":
            _print_list(ledger)
        elif args.aggregation_command == "report":
            _print_report(ledger, full_collapse=args.full_collapse)
        elif args.aggregation_command == "to-extxyz":
            count = ledger.to_extxyz(
                args.destination,
                aggregation_id=args.aggregation_id,
                energy_label=args.energy_label,
                forces_label=args.forces_label,
                node_energy_label=args.node_energy_label,
                include_node_energy=args.include_node_energy,
            )
            print(f"Wrote {count} frames to {args.destination}")
        else:
            if args.format == "html":
                _print_html(
                    ledger,
                    args.aggregation_id,
                    full_collapse=args.full_collapse,
                )
            else:
                _print_show(
                    ledger,
                    args.aggregation_id,
                    args.details,
                    args.structure_id,
                )
    except (
        AggregationValidationError,
        AggregationNotFoundError,
        RecordNotFoundError,
        StrictSelectionError,
        sqlite3.DatabaseError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
