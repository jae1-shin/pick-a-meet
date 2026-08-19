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

DEMO_MEETINGS = (
    {
        "place_name": "광교 모임 라운지",
        "start_at": (2026, 9, 5, 19, 0),
        "end_at": (2026, 9, 5, 21, 0),
        "description": "가볍게 저녁을 먹으며 서로의 관심사를 나누는 모임입니다.",
        "capacity": 10,
    },
    {
        "place_name": "서울숲 브런치 테이블",
        "start_at": (2026, 9, 12, 11, 30),
        "end_at": (2026, 9, 12, 13, 30),
        "description": "서울숲 근처에서 브런치를 즐기는 소규모 모임입니다.",
        "capacity": 4,
    },
    {
        "place_name": "강남 보드게임 카페",
        "start_at": (2026, 9, 18, 18, 30),
        "end_at": (2026, 9, 18, 21, 30),
        "description": "초보자도 편하게 참여할 수 있는 보드게임 저녁입니다.",
        "capacity": 6,
    },
    {
        "place_name": "광교호수공원 러닝",
        "start_at": (2026, 9, 23, 19, 30),
        "end_at": (2026, 9, 23, 21, 0),
        "description": "천천히 5km를 달리고 산책으로 마무리합니다.",
        "capacity": 12,
    },
    {
        "place_name": "수원 쿠킹 스튜디오",
        "start_at": (2026, 10, 2, 18, 30),
        "end_at": (2026, 10, 2, 21, 0),
        "description": "함께 파스타를 만들고 저녁을 나누는 체험 모임입니다.",
        "capacity": 5,
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

        seoul = ZoneInfo("Asia/Seoul")
        leader = users["leader01"]
        for item in DEMO_MEETINGS:
            meeting = await session.scalar(
                select(Meeting).where(Meeting.place_name == item["place_name"])
            )
            if meeting is None:
                meeting = Meeting(
                    place_name=item["place_name"],
                    start_at=datetime(*item["start_at"], tzinfo=seoul),
                    end_at=datetime(*item["end_at"], tzinfo=seoul),
                    description_content=item["description"],
                    capacity=item["capacity"],
                    status="OPEN",
                )
                session.add(meeting)
                await session.flush()
            host = await session.scalar(
                select(MeetingHost).where(MeetingHost.meeting_id == meeting.meeting_id)
            )
            if host is None:
                session.add(
                    MeetingHost(
                        meeting_id=meeting.meeting_id,
                        member_id=leader.member_id,
                    )
                )

        await session.commit()
        print("Demo data ready: 3 users, 5 open meetings")


if __name__ == "__main__":
    asyncio.run(seed())
