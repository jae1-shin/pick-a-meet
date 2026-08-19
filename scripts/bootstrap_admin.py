import asyncio
import os

from sqlalchemy import or_, select

from app.database import SessionFactory, engine
from app.models import Member, Module, Part


REQUIRED_ENV = (
    "BOOTSTRAP_ADMIN_LOGIN_ID",
    "BOOTSTRAP_ADMIN_EMPLOYEE_NO",
    "BOOTSTRAP_ADMIN_NAME",
    "BOOTSTRAP_ADMIN_PART",
    "BOOTSTRAP_ADMIN_MODULE",
)


def bootstrap_values() -> dict[str, str]:
    values = {name: os.environ.get(name, "").strip() for name in REQUIRED_ENV}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"Missing bootstrap settings: {', '.join(missing)}")
    return values


async def bootstrap_admin() -> None:
    values = bootstrap_values()
    async with SessionFactory() as session, session.begin():
        part = await session.scalar(
            select(Part).where(Part.name == values["BOOTSTRAP_ADMIN_PART"])
        )
        if part is None:
            part = Part(name=values["BOOTSTRAP_ADMIN_PART"])
            session.add(part)
            await session.flush()

        module = await session.scalar(
            select(Module).where(
                Module.part_id == part.part_id,
                Module.name == values["BOOTSTRAP_ADMIN_MODULE"],
            )
        )
        if module is None:
            module = Module(
                part_id=part.part_id,
                name=values["BOOTSTRAP_ADMIN_MODULE"],
            )
            session.add(module)
            await session.flush()

        member = await session.scalar(
            select(Member).where(
                or_(
                    Member.login_id == values["BOOTSTRAP_ADMIN_LOGIN_ID"],
                    Member.employee_no
                    == values["BOOTSTRAP_ADMIN_EMPLOYEE_NO"],
                )
            )
        )
        if member is not None and (
            member.login_id != values["BOOTSTRAP_ADMIN_LOGIN_ID"]
            or member.employee_no != values["BOOTSTRAP_ADMIN_EMPLOYEE_NO"]
        ):
            raise RuntimeError(
                "Login ID or employee number is already used by another member"
            )
        if member is None:
            member = Member(
                login_id=values["BOOTSTRAP_ADMIN_LOGIN_ID"],
                employee_no=values["BOOTSTRAP_ADMIN_EMPLOYEE_NO"],
                name=values["BOOTSTRAP_ADMIN_NAME"],
                module_id=module.module_id,
                active=True,
                apply_enabled=True,
                host_enabled=False,
                admin_enabled=True,
            )
            session.add(member)
        else:
            member.name = values["BOOTSTRAP_ADMIN_NAME"]
            member.module_id = module.module_id
            member.active = True
            member.admin_enabled = True
            if member.host_enabled:
                member.apply_enabled = False

    await engine.dispose()
    print(
        "Bootstrap Admin is ready:",
        values["BOOTSTRAP_ADMIN_LOGIN_ID"],
    )


if __name__ == "__main__":
    asyncio.run(bootstrap_admin())
