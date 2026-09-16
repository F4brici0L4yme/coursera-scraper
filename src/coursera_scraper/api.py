"""Coursera internal API client.

Uses the same undocumented ``onDemand*`` endpoints that the web app calls.
The course structure and lecture-video endpoints return pre-signed media URLs,
so no browser is required. An optional ``CAUTH`` cookie enables enrollment
checks and access to otherwise gated content.
"""

from __future__ import annotations

import dataclasses

import requests

BASE = "https://api.coursera.org"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 coursera-scraper/0.1"
)

# onDemandCourseMaterials.v1 is deprecated; use .v2 (response keys end in ".v2").
COURSE_MATERIALS_V2 = (
    BASE + "/api/onDemandCourseMaterials.v2/?q=slug&slug={slug}"
    "&includes=modules,lessons,passableItemGroups,passableItemGroupChoices,"
    "passableLessonElements,items,tracks,gradePolicy"
    "&fields=moduleIds,"
    "onDemandCourseMaterialModules.v1(name,slug,lessonIds),"
    "onDemandCourseMaterialLessons.v1(name,slug,elementIds),"
    "onDemandCourseMaterialItems.v2(name,slug,contentSummary,isLocked,"
    "itemLockedReasonCode,moduleId,lessonId)"
    "&showLockedItems=true"
)

LECTURE_VIDEOS = (
    BASE + "/api/onDemandLectureVideos.v1/{course_id}~{item_id}"
    "?includes=video&fields=onDemandVideos.v1(sources,subtitles,subtitlesVtt,subtitlesTxt)"
)

MEMBERSHIPS = (
    BASE + "/api/memberships.v1?includes=courseId,courses.v1"
    "&q=me&showHidden=true&filter=current,preEnrolled"
)

SUPPLEMENTS = BASE + "/api/onDemandSupplements.v1/{course_id}~{item_id}?includes=asset"

LECTURE_ASSETS = (
    BASE + "/api/onDemandLectureAssets.v1/{course_id}~{item_id}/?includes=openCourseAssets"
)

ASSETS_V1 = BASE + "/api/assets.v1?ids={ids}"


class CourseraError(Exception):
    """Base error for API failures."""


class AuthError(CourseraError):
    """Session missing or expired (401/403 from the API)."""


@dataclasses.dataclass
class Item:
    id: str
    name: str
    slug: str
    type_name: str | None
    is_locked: bool


@dataclasses.dataclass
class Lesson:
    id: str
    name: str
    slug: str
    item_ids: list[str]


@dataclasses.dataclass
class Module:
    id: str
    name: str
    slug: str
    lessons: list[Lesson]


@dataclasses.dataclass
class Course:
    id: str
    slug: str
    modules: list[Module]
    items: dict[str, Item]


class CourseraClient:
    def __init__(self, cauth: str | None = None):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.cauth = cauth
        if cauth:
            self.session.cookies.set("CAUTH", cauth, domain=".coursera.org")

    def _get_json(self, url: str) -> dict:
        resp = self.session.get(url, timeout=30)
        if resp.status_code in (401, 403):
            raise AuthError(
                f"Request rejected ({resp.status_code}). "
                "Your CAUTH cookie may be missing or expired."
            )
        resp.raise_for_status()
        return resp.json()

    def get_course(self, slug: str) -> Course:
        data = self._get_json(COURSE_MATERIALS_V2.format(slug=slug))
        elements = data.get("elements") or []
        if not elements:
            raise CourseraError(f"Course not found for slug '{slug}'.")
        linked = data.get("linked") or {}

        modules_by_id = {m["id"]: m for m in linked.get("onDemandCourseMaterialModules.v1", [])}
        lessons_by_id = {
            lsn["id"]: lsn for lsn in linked.get("onDemandCourseMaterialLessons.v1", [])
        }
        items_by_id = {i["id"]: i for i in linked.get("onDemandCourseMaterialItems.v2", [])}

        course_id = elements[0]["id"]
        modules: list[Module] = []
        for module_id in elements[0].get("moduleIds", []):
            mod = modules_by_id.get(module_id)
            if not mod:
                continue
            lessons: list[Lesson] = []
            for lesson_id in mod.get("lessonIds", []):
                les = lessons_by_id.get(lesson_id)
                if not les:
                    continue
                item_ids = [
                    e.split("~", 1)[1]
                    for e in les.get("elementIds", [])
                    if isinstance(e, str) and e.startswith("item~")
                ]
                lessons.append(
                    Lesson(
                        id=lesson_id,
                        name=les.get("name", ""),
                        slug=les.get("slug", ""),
                        item_ids=item_ids,
                    )
                )
            modules.append(
                Module(
                    id=module_id,
                    name=mod.get("name", ""),
                    slug=mod.get("slug", ""),
                    lessons=lessons,
                )
            )

        items: dict[str, Item] = {}
        for item_id, it in items_by_id.items():
            content = it.get("contentSummary") or {}
            items[item_id] = Item(
                id=item_id,
                name=it.get("name", ""),
                slug=it.get("slug", ""),
                type_name=content.get("typeName"),
                is_locked=bool(it.get("isLocked")),
            )

        return Course(id=course_id, slug=slug, modules=modules, items=items)

    def get_lecture_video(self, course_id: str, item_id: str) -> dict | None:
        data = self._get_json(LECTURE_VIDEOS.format(course_id=course_id, item_id=item_id))
        videos = (data.get("linked") or {}).get("onDemandVideos.v1") or []
        return videos[0] if videos else None

    def get_supplement(self, course_id: str, item_id: str) -> dict | None:
        """Return the rendered definition of a reading/supplement item, or None.

        The definition carries ``renderableHtmlWithMetadata`` (rendered HTML +
        flags) and the raw CML ``value``.
        """
        data = self._get_json(SUPPLEMENTS.format(course_id=course_id, item_id=item_id))
        assets = (data.get("linked") or {}).get("openCourseAssets.v1") or []
        for asset in assets:
            if asset.get("typeName") == "cml":
                return asset.get("definition")
        return None

    def get_lecture_assets(self, course_id: str, item_id: str) -> list[str]:
        """Return the asset ids (slides/PDFs) attached to a lecture."""
        data = self._get_json(LECTURE_ASSETS.format(course_id=course_id, item_id=item_id))
        assets = (data.get("linked") or {}).get("openCourseAssets.v1") or []
        ids = []
        for asset in assets:
            asset_id = (asset.get("definition") or {}).get("assetId")
            if asset_id:
                # ids may carry a trailing "@N" version suffix to strip
                ids.append(asset_id.split("@")[0])
        return ids

    def get_asset_files(self, asset_ids: list[str]) -> list[dict]:
        """Resolve asset ids to signed download URLs.

        Returns a list of ``{"name", "url", "type_name"}`` dicts.
        """
        if not asset_ids:
            return []
        data = self._get_json(ASSETS_V1.format(ids=",".join(asset_ids)))
        files = []
        for element in data.get("elements") or []:
            url = (element.get("url") or {}).get("url")
            name = element.get("name") or ""
            if url:
                files.append({"name": name, "url": url, "type_name": element.get("typeName")})
        return files

    def enrolled_slugs(self) -> set[str]:
        """Return the set of course slugs the account is enrolled in (needs CAUTH)."""
        data = self._get_json(MEMBERSHIPS)
        return {
            c.get("slug") for c in (data.get("linked") or {}).get("courses.v1", []) if c.get("slug")
        }
