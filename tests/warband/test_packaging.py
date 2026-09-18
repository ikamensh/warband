"""The frozen diagnostic and package description, checked before anything is built."""
import importlib.util

import pytest

from saga2d.packaging.verify import local_server
from tools.package import PACKAGE


def package_check():
    spec = importlib.util.spec_from_file_location("package_check", PACKAGE.check)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return checker


def test_package_names_existing_entry_documents_and_diagnostics():
    assert PACKAGE.check.is_file()
    assert (PACKAGE.root / PACKAGE.package / "__main__.py").is_file()
    for origin in PACKAGE.documents.values():
        assert (PACKAGE.root / origin).is_file(), origin


@pytest.mark.slow
def test_shipped_smoke_accepts_authority_movement_and_seat_rejoin():
    """The exact frozen diagnostic uses production room rules and both real clients.

    The shipped smoke runs its whole online journey against a real server, over a second: the slow tier."""
    with local_server(PACKAGE.online) as endpoint:
        result = package_check().online_smoke(endpoint)
    assert result == {"create_join": True, "foreign_order_rejected": True, "authoritative_movement": True,
                      "private_seat_rejoin": True, "global_production": True, "automatic_plan_builder": True,
                      "assembly_point": True, "cancel_plans": True}
