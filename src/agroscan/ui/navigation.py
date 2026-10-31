"""Page registry: every page is addressed by ``PageKey``, never by index (P-006).

Sidebar order, sections and role visibility all come from ``PAGE_SPECS``.
Adding, removing or reordering a page only touches this table.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from agroscan.models.user_models import Role


class PageKey(Enum):
    DASHBOARD          = "dashboard"
    BOX_INTAKE         = "box_intake"
    REVIEW_QUEUE       = "review_queue"
    INSPECTION_HISTORY = "inspection_history"
    REPORTS            = "reports"
    DATA_IMPORT        = "data_import"
    CATALOG            = "catalog"
    USERS              = "users"
    SETTINGS           = "settings"
    # Workflow steps — not shown on the sidebar
    LIVE_INSPECTION    = "live_inspection"
    ASSESSMENT_RESULT  = "assessment_result"


class NavSection(Enum):
    OPERATIONS     = "OPERATIONS"
    RECORDS        = "RECORDS"
    ADMINISTRATION = "ADMINISTRATION"


_ALL_ROLES   = frozenset(Role)
_ADMIN       = frozenset({Role.ADMIN})
_INSPECTION  = frozenset({Role.ADMIN, Role.INSPECTOR})
_REVIEW      = frozenset({Role.ADMIN, Role.REVIEWER})


@dataclass(frozen=True)
class PageSpec:
    key:     PageKey
    label:   str
    roles:   frozenset[Role]
    section: Optional[NavSection] = None   # None → workflow step, not on sidebar
    parent:  Optional[PageKey] = None      # Sidebar item highlighted for workflow steps
    is_heavy: bool = False                 # Show loading screen before opening


PAGE_SPECS: tuple[PageSpec, ...] = (
    PageSpec(PageKey.DASHBOARD,          "Dashboard",          _ALL_ROLES,  NavSection.OPERATIONS),
    PageSpec(PageKey.BOX_INTAKE,         "Box Intake",         _INSPECTION, NavSection.OPERATIONS),
    PageSpec(PageKey.REVIEW_QUEUE,       "Review Queue",       _REVIEW,     NavSection.OPERATIONS, is_heavy=True),
    PageSpec(PageKey.INSPECTION_HISTORY, "Inspection History", _ALL_ROLES,  NavSection.RECORDS, is_heavy=True),
    PageSpec(PageKey.REPORTS,            "Reports",            _ALL_ROLES,  NavSection.RECORDS, is_heavy=True),
    PageSpec(PageKey.DATA_IMPORT,        "Data Import",        _ADMIN,      NavSection.ADMINISTRATION),
    PageSpec(PageKey.CATALOG,            "Catalog & Criteria", _ADMIN,      NavSection.ADMINISTRATION),
    PageSpec(PageKey.USERS,              "Users",              _ADMIN,      NavSection.ADMINISTRATION),
    PageSpec(PageKey.SETTINGS,           "Settings",           _ADMIN,      NavSection.ADMINISTRATION),
    PageSpec(PageKey.LIVE_INSPECTION,    "Live Inspection",    _INSPECTION, parent=PageKey.BOX_INTAKE),
    PageSpec(PageKey.ASSESSMENT_RESULT,  "Assessment Result",  _INSPECTION, parent=PageKey.BOX_INTAKE),
)

_SPECS_BY_KEY: dict[PageKey, PageSpec] = {spec.key: spec for spec in PAGE_SPECS}


def get_spec(key: PageKey) -> PageSpec:
    return _SPECS_BY_KEY[key]


def can_access(role: Role, key: PageKey) -> bool:
    return role in _SPECS_BY_KEY[key].roles


def sidebar_specs(role: Role) -> list[PageSpec]:
    """Các mục sidebar mà vai trò được thấy, giữ thứ tự của ``PAGE_SPECS``.

    Mục không có quyền bị ẩn hẳn (không hiển thị mờ).
    """
    return [s for s in PAGE_SPECS if s.section is not None and role in s.roles]
