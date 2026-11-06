// Notebook widget (anywidget) for stoms.viewer.Viewer.
//
// The viewer itself is the self-contained page of stoms/viewer/document.py
// (viewer.js with embed.js), shown in an iframe so that every viewer in a
// notebook has its own settings and camera. This module only relays state:
// model traits frame, settings and camera go to the page; the page's
// snapshots ({ state, svg }) come back as those traits and _snapshot. The
// page's requests for what Python computes (phonons: { type: "api", id, path })
// go to the kernel, and its replies back to the page. See embed.js for the
// messages.

export default {
  render({ model, el }) {
    const frame = document.createElement("iframe");
    frame.title = "STOMS viewer";
    frame.style.cssText = "display:block;width:100%;height:500px;border:0;";
    el.append(frame);

    const post = (message) => frame.contentWindow?.postMessage({ stoms: true, ...message }, "*");
    const state = () => ({ frame: model.get("frame"), settings: model.get("settings"), camera: model.get("camera") });
    // While the page's own state is stored, its change events are not sent back.
    let storing = false;
    const toPage = () => { if (!storing) post({ type: "state", ...state() }); };

    const onMessage = (event) => {
      const m = event.data;
      if (event.source !== frame.contentWindow || !m || !m.stoms) return;
      if (m.type === "ready") toPage();
      else if (m.type === "size" && m.height > 0) frame.style.height = `${m.height}px`;
      else if (m.type === "api") model.send({ type: "api", id: m.id, path: m.path });
      else if (m.type === "snapshot") {
        storing = true;
        try {
          model.set("frame", m.state.frame);
          model.set("settings", m.state.settings);
          model.set("camera", m.state.camera);
          model.set("_snapshot", { state: m.state, svg: m.svg });
          if (Array.isArray(m.measurements)) model.set("_measurements", m.measurements);
          model.save_changes();
        } finally {
          storing = false;
        }
      }
    };
    const onCustom = (message) => {
      if (message?.type === "view") post({ type: "view", name: message.name });
      else if (message?.type === "api") post({ type: "api", id: message.id, data: message.data, error: message.error });
    };
    const load = () => { frame.srcdoc = model.get("_document"); };

    window.addEventListener("message", onMessage);
    model.on("change:frame", toPage);
    model.on("change:settings", toPage);
    model.on("change:camera", toPage);
    model.on("change:_document", load);
    model.on("msg:custom", onCustom);
    load();

    return () => {
      window.removeEventListener("message", onMessage);
      model.off("change:frame", toPage);
      model.off("change:settings", toPage);
      model.off("change:camera", toPage);
      model.off("change:_document", load);
      model.off("msg:custom", onCustom);
    };
  },
};
