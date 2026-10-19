import stoms.atomsledger as atomsledger
import stoms.atomsledger.backends as backends


def test_supported_backends_are_public() -> None:
    for module in (atomsledger, backends):
        assert "HDF5Repository" not in module.__all__
        assert "PostgresRepository" in module.__all__
        assert not hasattr(module, "HDF5Repository")
        assert hasattr(module, "PostgresRepository")

    assert not hasattr(atomsledger.AtomsLedger, "export_database_hdf5")
    assert not hasattr(atomsledger.AtomsLedger, "import_database_hdf5")
