import json
import os
import sys
import unittest
from pathlib import Path

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.modules.dict.init_db import run as init_dict  # noqa: E402
from app.modules.dict.model.dict import DictInfo, DictType  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def _flatten_menu(items: list[dict], parent_code: str | None = None):
    for item in items:
        current = dict(item)
        children = current.pop("children", []) or []
        if parent_code and not current.get("parent_code"):
            current["parent_code"] = parent_code
        yield current
        yield from _flatten_menu(children, current.get("code"))


class InitializationAlignmentTests(unittest.TestCase):
    def test_menu_manifests_reference_valid_frontend_assets(self):
        menu_files = sorted((BACKEND / "app" / "modules").glob("*/menu.json"))
        items: list[dict] = []

        for menu_file in menu_files:
            with menu_file.open("r", encoding="utf-8") as file:
                items.extend(_flatten_menu(json.load(file)))

        codes: dict[str, list[dict]] = {}
        permissions: dict[str, list[str]] = {}
        paths: dict[str, list[str]] = {}
        missing_parents: list[str] = []
        missing_components: list[str] = []
        missing_icons: list[str] = []
        svg_dirs = {path.parent for path in (FRONTEND / "src" / "modules").glob("*/static/svg/*.svg")}

        for item in items:
            code = item.get("code")
            if code:
                codes.setdefault(code, []).append(item)
            if item.get("permission"):
                permissions.setdefault(item["permission"], []).append(code)
            if item.get("path"):
                paths.setdefault(item["path"], []).append(code)

        for item in items:
            code = item.get("code")
            parent_code = item.get("parent_code")
            if parent_code and parent_code not in codes:
                missing_parents.append(f"{code} -> {parent_code}")

            component = item.get("component")
            if component and component != "layout":
                component_path = FRONTEND / "src" / component.replace("cool/", "")
                if not component_path.exists():
                    missing_components.append(f"{code} -> {component}")

            icon = item.get("icon")
            if icon and icon.startswith("icon-"):
                if not any((svg_dir / f"{icon}.svg").exists() for svg_dir in svg_dirs):
                    missing_icons.append(f"{code} -> {icon}")

        duplicate_codes = {key: len(value) for key, value in codes.items() if len(value) > 1}
        duplicate_permissions = {key: value for key, value in permissions.items() if len(value) > 1}
        duplicate_paths = {key: value for key, value in paths.items() if len(value) > 1}

        self.assertEqual(duplicate_codes, {})
        self.assertEqual(duplicate_permissions, {})
        self.assertEqual(duplicate_paths, {})
        self.assertEqual(missing_parents, [])
        self.assertEqual(missing_components, [])
        self.assertEqual(missing_icons, [])

    def test_dict_initialization_creates_ordered_status_values(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine, tables=[DictType.__table__, DictInfo.__table__])

        with Session(engine) as session:
            init_dict(session)
            status_dict = session.exec(select(DictType).where(DictType.key == "status")).one()
            values = session.exec(
                select(DictInfo)
                .where(DictInfo.type_id == status_dict.id)
                .order_by(DictInfo.sort_order)
            ).all()

            self.assertEqual([(item.name, item.value, item.sort_order) for item in values], [
                ("禁用", "0", 0),
                ("启用", "1", 1),
            ])

            init_dict(session)
            values_after_second_run = session.exec(
                select(DictInfo).where(DictInfo.type_id == status_dict.id)
            ).all()
            self.assertEqual(len(values_after_second_run), 2)


if __name__ == "__main__":
    unittest.main()
