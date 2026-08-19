import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.database import SessionFactory
from app.models import (
    Meeting,
    MeetingHost,
    Member,
    Module,
    Part,
    Registration,
    RegistrationHistory,
)


LEADER_PROFILES = (
    ("이리더", "플랫폼파트", "서비스개발모듈"),
    ("정리더", "데이터파트", "데이터분석모듈"),
    ("최리더", "사업파트", "서비스기획모듈"),
    ("한리더", "디자인파트", "UX모듈"),
    ("오리더", "인프라파트", "클라우드모듈"),
)

MEMBER_PROFILES = (
    ("박일반", "플랫폼파트", "서비스개발모듈"),
    ("김하늘", "플랫폼파트", "프론트엔드모듈"),
    ("이바다", "데이터파트", "데이터분석모듈"),
    ("정다온", "데이터파트", "AI모듈"),
    ("최가람", "사업파트", "서비스기획모듈"),
    ("한누리", "사업파트", "마케팅모듈"),
    ("오서윤", "디자인파트", "UX모듈"),
    ("윤지호", "디자인파트", "브랜드모듈"),
    ("장유진", "인프라파트", "클라우드모듈"),
    ("임시우", "인프라파트", "보안모듈"),
    ("송민재", "경영지원파트", "서비스운영모듈"),
)

DEMO_USERS = (
    {
        "login_id": "admin01",
        "employee_no": "1",
        "name": "김관리",
        "part": "경영지원파트",
        "module": "서비스운영모듈",
        "admin_enabled": True,
        "host_enabled": False,
    },
) + tuple(
    {
        "login_id": f"leader{index:02d}",
        "employee_no": str(index + 1),
        "name": name,
        "part": part,
        "module": module,
        "admin_enabled": False,
        "host_enabled": True,
    }
    for index, (name, part, module) in enumerate(LEADER_PROFILES, start=1)
) + tuple(
    {
        "login_id": f"member{index:02d}",
        "employee_no": str(index + 6),
        "name": name,
        "part": part,
        "module": module,
        "admin_enabled": False,
        "host_enabled": False,
    }
    for index, (name, part, module) in enumerate(MEMBER_PROFILES, start=1)
)

DEMO_MEETINGS = (
    {
        "place_name": "광교 모임 라운지",
        "place_url": "https://map.naver.com/p/search/광교중앙역",
        "neighborhood": "광교",
        "representative_menu": "파스타와 피자",
        "host_message": "편하게 이야기 나누며 좋은 저녁 보내요!",
        "host_login_id": "leader01",
        "start_at": (2026, 9, 5, 19, 0),
        "end_at": (2026, 9, 5, 21, 0),
        "description": "가볍게 저녁을 먹으며 서로의 관심사를 나누는 모임입니다.",
        "capacity": 10,
    },
    {
        "place_name": "서울숲 브런치 테이블",
        "place_url": "https://map.naver.com/p/search/서울숲",
        "neighborhood": "성수·서울숲",
        "representative_menu": "브런치 플래터",
        "host_message": "주말 낮에 가볍게 만나 맛있는 브런치 먹어요.",
        "host_login_id": "leader02",
        "start_at": (2026, 9, 12, 11, 30),
        "end_at": (2026, 9, 12, 13, 30),
        "description": "서울숲 근처에서 브런치를 즐기는 소규모 모임입니다.",
        "capacity": 4,
    },
    {
        "place_name": "강남 보드게임 카페",
        "place_url": "https://map.naver.com/p/search/강남역 보드게임카페",
        "neighborhood": "강남",
        "representative_menu": "보드게임과 스낵",
        "host_message": "룰을 몰라도 괜찮아요. 제가 차근차근 알려드릴게요!",
        "host_login_id": "leader03",
        "start_at": (2026, 9, 18, 18, 30),
        "end_at": (2026, 9, 18, 21, 30),
        "description": "초보자도 편하게 참여할 수 있는 보드게임 저녁입니다.",
        "capacity": 6,
    },
    {
        "place_name": "광교호수공원 러닝",
        "place_url": "https://map.naver.com/p/search/광교호수공원",
        "neighborhood": "광교",
        "representative_menu": "러닝 후 이온음료",
        "host_message": "기록보다 함께 완주하는 게 목표입니다.",
        "host_login_id": "leader04",
        "start_at": (2026, 9, 23, 19, 30),
        "end_at": (2026, 9, 23, 21, 0),
        "description": "천천히 5km를 달리고 산책으로 마무리합니다.",
        "capacity": 12,
    },
    {
        "place_name": "수원 쿠킹 스튜디오",
        "place_url": "https://map.naver.com/p/search/수원 쿠킹스튜디오",
        "neighborhood": "수원역·행궁동",
        "representative_menu": "생면 파스타",
        "host_message": "요리를 처음 해보는 분도 환영합니다!",
        "host_login_id": "leader05",
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
            else:
                member.employee_no = item["employee_no"]
                member.name = item["name"]
                member.module_id = module.module_id
                member.admin_enabled = item["admin_enabled"]
                member.host_enabled = item["host_enabled"]
                member.apply_enabled = True
                member.active = True
            users[item["login_id"]] = member

        seoul = ZoneInfo("Asia/Seoul")
        meetings: dict[str, Meeting] = {}
        for item in DEMO_MEETINGS:
            meeting = await session.scalar(
                select(Meeting).where(Meeting.place_name == item["place_name"])
            )
            if meeting is None:
                meeting = Meeting(
                    place_name=item["place_name"],
                    place_url=item["place_url"],
                    neighborhood=item["neighborhood"],
                    representative_menu=item["representative_menu"],
                    host_message=item["host_message"],
                    start_at=datetime(*item["start_at"], tzinfo=seoul),
                    end_at=datetime(*item["end_at"], tzinfo=seoul),
                    description_content="",
                    capacity=item["capacity"],
                    status="OPEN",
                )
                session.add(meeting)
                await session.flush()
            else:
                meeting.place_url = item["place_url"]
                meeting.neighborhood = item["neighborhood"]
                meeting.representative_menu = item["representative_menu"]
                meeting.host_message = item["host_message"]
                meeting.description_content = ""
                meeting.capacity = item["capacity"]
            meetings[item["place_name"]] = meeting
            leader = users[item["host_login_id"]]
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
            else:
                host.member_id = leader.member_id

        sample_assignments = (
            ("member02", "광교 모임 라운지"),
            ("member03", "광교 모임 라운지"),
            ("member04", "서울숲 브런치 테이블"),
            ("member05", "강남 보드게임 카페"),
            ("member06", "광교호수공원 러닝"),
            ("member07", "수원 쿠킹 스튜디오"),
        )
        for login_id, place_name in sample_assignments:
            member = users[login_id]
            existing = await session.scalar(
                select(Registration).where(Registration.member_id == member.member_id)
            )
            if existing is None:
                meeting = meetings[place_name]
                session.add(
                    Registration(
                        member_id=member.member_id,
                        meeting_id=meeting.meeting_id,
                    )
                )
                session.add(
                    RegistrationHistory(
                        member_id=member.member_id,
                        meeting_id=meeting.meeting_id,
                        action="APPLY",
                    )
                )

        await session.commit()
        print("Demo data ready: 1 admin, 5 leaders, 11 members, 5 meetings")


if __name__ == "__main__":
    asyncio.run(seed())
