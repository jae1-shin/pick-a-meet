import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.database import SessionFactory
from app.models import Meeting, MeetingHost, Member, Module, Part


DEMO_USERS = (
    {
        "login_id": "admin01",
        "employee_no": "10000001",
        "name": "김관리",
        "part": "경영지원파트",
        "module": "서비스운영모듈",
        "admin_enabled": True,
        "host_enabled": False,
    },
    {
        "login_id": "leader01",
        "employee_no": "10000002",
        "name": "이리더",
        "part": "플랫폼파트",
        "module": "서비스개발모듈",
        "admin_enabled": False,
        "host_enabled": True,
    },
    {
        "login_id": "member01",
        "employee_no": "10000003",
        "name": "박일반",
        "part": "플랫폼파트",
        "module": "서비스개발모듈",
        "admin_enabled": False,
        "host_enabled": False,
    },
)


async def get_or_create_module(session, part_name: str, module_name: str) -> Module:
    part = await session.scalar(select(Part).where(Part.name == part_name))
    if part is None:
        part = Part(name=part_name)
        session.add(part)
        await session.flush()

    module = await session.scalar(
        select(Module).where(Module.part_id == part.part_id, Module.name == module_name)
    )
    if module is None:
        module = Module(part_id=part.part_id, name=module_name)
        session.add(module)
        await session.flush()
    return module


async def seed() -> None:
    async with SessionFactory() as session:
        users: dict[str, Member] = {}
        for item in DEMO_USERS:
            module = await get_or_create_module(session, item["part"], item["module"])
            member = await session.scalar(
                select(Member).where(Member.login_id == item["login_id"])
            )
            if member is None:
                member = Member(
                    login_id=item["login_id"],
                    employee_no=item["employee_no"],
                    name=item["name"],
                    module_id=module.module_id,
                    admin_enabled=item["admin_enabled"],
                    host_enabled=item["host_enabled"],
                    apply_enabled=True,
                    active=True,
                )
                session.add(member)
                await session.flush()
            users[item["login_id"]] = member

        meeting = await session.scalar(
            select(Meeting).where(Meeting.place_name == "광교 모임 라운지")
        )
        if meeting is None:
            seoul = ZoneInfo("Asia/Seoul")
            meeting = Meeting(
                place_name="광교 모임 라운지",
                start_at=datetime(2026, 9, 5, 19, 0, tzinfo=seoul),
                end_at=datetime(2026, 9, 5, 21, 0, tzinfo=seoul),
                description_content="첫 번째 Pick a Meet 데모 모임입니다.",
                capacity=10,
                status="OPEN",
            )
            session.add(meeting)
            await session.flush()
            session.add(
                MeetingHost(
                    meeting_id=meeting.meeting_id,
                    member_id=users["leader01"].member_id,
                )
            )

        await session.commit()
        print("Demo data ready: admin01, leader01, member01")


if __name__ == "__main__":
    asyncio.run(seed())
