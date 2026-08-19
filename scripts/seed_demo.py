import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete

from app.database import SessionFactory, engine
from app.models import (
    LoginHistory,
    Meeting,
    MeetingHost,
    Member,
    Module,
    Part,
    Registration,
    RegistrationHistory,
)


PART_SPECS = (
    {
        "name": "플랫폼파트",
        "modules": ("서비스개발모듈", "프론트엔드모듈", "플랫폼운영모듈"),
        "leader_count": 4,
        "member_numbers": range(19, 47),
    },
    {
        "name": "데이터파트",
        "modules": ("데이터분석모듈", "AI모듈", "데이터플랫폼모듈"),
        "leader_count": 4,
        "member_numbers": range(47, 73),
    },
    {
        "name": "사업파트",
        "modules": ("서비스기획모듈", "마케팅모듈", "사업운영모듈"),
        "leader_count": 4,
        "member_numbers": range(73, 97),
    },
    {
        "name": "디자인파트",
        "modules": ("UX모듈", "브랜드모듈"),
        "leader_count": 3,
        "member_numbers": range(97, 109),
    },
    {
        "name": "인프라파트",
        "modules": ("클라우드모듈", "보안모듈"),
        "leader_count": 3,
        "member_numbers": range(109, 121),
    },
)


def build_demo_users() -> tuple[dict[str, object], ...]:
    users: list[dict[str, object]] = []
    leader_number = 1
    for part in PART_SPECS:
        for local_index in range(part["leader_count"]):
            number = leader_number
            users.append(
                {
                    "login_id": f"leader{number:02d}",
                    "employee_no": str(number),
                    "name": f"{part['name'].removesuffix('파트')}리더{local_index + 1:02d}",
                    "part": part["name"],
                    "module": part["modules"][local_index % len(part["modules"])],
                    "admin_enabled": number == 1,
                    "host_enabled": True,
                    "active": True,
                }
            )
            leader_number += 1

    for part in PART_SPECS:
        for local_index, number in enumerate(part["member_numbers"]):
            users.append(
                {
                    "login_id": f"member{number:02d}",
                    "employee_no": str(number),
                    "name": f"{part['name'].removesuffix('파트')}멤버{number:03d}",
                    "part": part["name"],
                    "module": part["modules"][local_index % len(part["modules"])],
                    "admin_enabled": number in (19, 20),
                    "host_enabled": False,
                    "active": True,
                }
            )
    return tuple(users)


DEMO_USERS = build_demo_users()


MEETING_THEMES = (
    ("광교 파스타 테이블", "광교", "파스타와 피자", "편하게 이야기 나누며 좋은 저녁 보내요!"),
    ("서울숲 브런치 테이블", "성수·서울숲", "브런치 플래터", "주말 낮에 가볍게 만나 맛있는 브런치 먹어요."),
    ("강남 보드게임 카페", "강남", "보드게임과 스낵", "룰을 몰라도 괜찮아요. 차근차근 알려드릴게요!"),
    ("광교호수공원 러닝", "광교", "러닝 후 이온음료", "기록보다 함께 완주하는 게 목표입니다."),
    ("수원 쿠킹 스튜디오", "수원역·행궁동", "생면 파스타", "요리를 처음 해보는 분도 환영합니다!"),
    ("판교 커피 라운지", "판교", "커피와 디저트", "일 이야기 없이 편하게 커피 한잔해요."),
    ("성수 베이커리 모임", "성수·서울숲", "빵과 커피", "새로 나온 빵을 같이 골라봐요."),
    ("강남 이자카야 저녁", "강남", "꼬치와 나베", "퇴근 후 가볍게 이야기 나눠요."),
    ("행궁동 산책 모임", "수원역·행궁동", "만두와 쫄면", "천천히 걷고 맛있는 것도 먹어요."),
    ("판교 점심 탐방", "판교", "솥밥", "점심시간을 알차게 보내봅시다."),
    ("광교 영화 이야기", "광교", "타코와 음료", "최근 본 영화를 편하게 추천해주세요."),
    ("서울숲 피크닉", "성수·서울숲", "샌드위치", "돗자리는 제가 준비할게요."),
    ("강남 방탈출", "강남", "방탈출 후 치킨", "초보도 즐길 수 있는 난이도로 골랐어요."),
    ("수원 사진 산책", "수원역·행궁동", "행궁동 디저트", "휴대폰 카메라만 있어도 충분합니다."),
    ("판교 독서 대화", "판교", "샐러드와 커피", "책을 다 읽지 못했어도 환영해요."),
    ("광교 야경 산책", "광교", "떡볶이", "가볍게 걷고 야식도 함께해요."),
    ("성수 전시 관람", "성수·서울숲", "수제버거", "전시를 보고 각자의 감상을 나눠요."),
    ("강남 공연 모임", "강남", "우동과 튀김", "좋아하는 음악 이야기도 함께 나눠요."),
)


def build_demo_meetings() -> tuple[dict[str, object], ...]:
    days = (1, 3, 5, 8, 10, 12)
    times = ((11, 30), (18, 30), (19, 30))
    meetings: list[dict[str, object]] = []
    for index, (place, neighborhood, menu, message) in enumerate(
        MEETING_THEMES, start=1
    ):
        day = days[(index - 1) // 3]
        hour, minute = times[(index - 1) % 3]
        meetings.append(
            {
                "place_name": place,
                "place_url": f"https://map.naver.com/p/search/{place}",
                "neighborhood": neighborhood,
                "representative_menu": menu,
                "host_message": message,
                "host_login_id": f"leader{index:02d}",
                "start_at": (2026, 9, day, hour, minute),
                "capacity": 8 + ((index - 1) % 3) * 2,
                "status": "CLOSED" if index in (17, 18) else "OPEN",
            }
        )
    return tuple(meetings)


DEMO_MEETINGS = build_demo_meetings()


def build_sample_assignments() -> tuple[tuple[str, str], ...]:
    member_logins_by_part = {
        part["name"]: [f"member{number:02d}" for number in part["member_numbers"]]
        for part in PART_SPECS
    }
    offsets = {part["name"]: 0 for part in PART_SPECS}
    overflow_parts = [part["name"] for part in PART_SPECS[:3]]
    assignments: list[tuple[str, str]] = []

    for meeting_index, meeting in enumerate(DEMO_MEETINGS[:10]):
        for part in PART_SPECS:
            part_name = part["name"]
            member_login = member_logins_by_part[part_name][offsets[part_name]]
            offsets[part_name] += 1
            assignments.append((member_login, meeting["place_name"]))
        if meeting_index < 9:
            part_name = overflow_parts[meeting_index % len(overflow_parts)]
            member_login = member_logins_by_part[part_name][offsets[part_name]]
            offsets[part_name] += 1
            assignments.append((member_login, meeting["place_name"]))
    return tuple(assignments)


SAMPLE_ASSIGNMENTS = build_sample_assignments()


async def clear_demo_data(session) -> None:
    for model in (
        RegistrationHistory,
        Registration,
        MeetingHost,
        LoginHistory,
        Meeting,
        Member,
        Module,
        Part,
    ):
        await session.execute(delete(model))


async def seed() -> None:
    async with SessionFactory() as session, session.begin():
        await clear_demo_data(session)

        modules: dict[tuple[str, str], Module] = {}
        for spec in PART_SPECS:
            part = Part(name=spec["name"])
            session.add(part)
            await session.flush()
            for module_name in spec["modules"]:
                module = Module(part_id=part.part_id, name=module_name)
                session.add(module)
                await session.flush()
                modules[(spec["name"], module_name)] = module

        users: dict[str, Member] = {}
        for item in DEMO_USERS:
            member = Member(
                login_id=item["login_id"],
                employee_no=item["employee_no"],
                name=item["name"],
                module_id=modules[(item["part"], item["module"])].module_id,
                admin_enabled=item["admin_enabled"],
                host_enabled=item["host_enabled"],
                apply_enabled=not item["host_enabled"],
                active=item["active"],
            )
            session.add(member)
            await session.flush()
            users[item["login_id"]] = member

        seoul = ZoneInfo("Asia/Seoul")
        meetings: dict[str, Meeting] = {}
        for item in DEMO_MEETINGS:
            meeting = Meeting(
                place_name=item["place_name"],
                place_url=item["place_url"],
                neighborhood=item["neighborhood"],
                representative_menu=item["representative_menu"],
                host_message=item["host_message"],
                start_at=datetime(*item["start_at"], tzinfo=seoul),
                description_content="",
                capacity=item["capacity"],
                status=item["status"],
            )
            session.add(meeting)
            await session.flush()
            meetings[item["place_name"]] = meeting
            session.add(
                MeetingHost(
                    meeting_id=meeting.meeting_id,
                    member_id=users[item["host_login_id"]].member_id,
                )
            )

        for login_id, place_name in SAMPLE_ASSIGNMENTS:
            member = users[login_id]
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

    await engine.dispose()
    print(
        "Demo data ready: 120 users, 18 leaders, 3 admins, "
        "18 meetings, 59 registrations"
    )


if __name__ == "__main__":
    asyncio.run(seed())
