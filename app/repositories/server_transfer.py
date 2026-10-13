import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.server import Server
from app.models.server_member import ServerMember
from app.models.server_ownership_transfer import ServerOwnershipTransfer


class ServerTransferRepository:
    async def get_server(self, db: AsyncSession, server_id: uuid.UUID) -> Server | None:
        return await db.scalar(select(Server).where(Server.id == server_id))

    async def is_member(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> bool:
        member_id = await db.scalar(
            select(ServerMember.id).where(ServerMember.server_id == server_id, ServerMember.user_id == user_id)
        )
        return member_id is not None

    async def get_transfer_by_id(
        self, db: AsyncSession, transfer_id: uuid.UUID
    ) -> ServerOwnershipTransfer | None:
        return await db.scalar(select(ServerOwnershipTransfer).where(ServerOwnershipTransfer.id == transfer_id))

    async def get_pending_transfer_for_server(
        self, db: AsyncSession, server_id: uuid.UUID
    ) -> ServerOwnershipTransfer | None:
        stmt = (
            select(ServerOwnershipTransfer)
            .where(ServerOwnershipTransfer.server_id == server_id, ServerOwnershipTransfer.status == "PENDING")
            .order_by(ServerOwnershipTransfer.created_at.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def get_pending_transfer_for_user(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str
    ) -> ServerOwnershipTransfer | None:
        stmt = (
            select(ServerOwnershipTransfer)
            .where(
                ServerOwnershipTransfer.server_id == server_id,
                ServerOwnershipTransfer.target_user_id == user_id,
                ServerOwnershipTransfer.status == "PENDING",
            )
            .order_by(ServerOwnershipTransfer.created_at.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def cancel_pending_transfers(self, db: AsyncSession, server_id: uuid.UUID) -> None:
        await db.execute(
            update(ServerOwnershipTransfer)
            .where(ServerOwnershipTransfer.server_id == server_id, ServerOwnershipTransfer.status == "PENDING")
            .values(status="CANCELLED")
        )

    async def create_transfer(
        self, db: AsyncSession, transfer: ServerOwnershipTransfer
    ) -> ServerOwnershipTransfer:
        db.add(transfer)
        await db.commit()
        await db.refresh(transfer)
        return transfer

    async def update_transfer_status(
        self, db: AsyncSession, transfer: ServerOwnershipTransfer, status: str
    ) -> ServerOwnershipTransfer:
        transfer.status = status
        await db.commit()
        await db.refresh(transfer)
        return transfer

    async def complete_ownership_transfer(
        self, db: AsyncSession, server: Server, transfer: ServerOwnershipTransfer, new_owner_id: str
    ) -> ServerOwnershipTransfer:
        server.owner_id = new_owner_id
        transfer.status = "ACCEPTED"
        await db.commit()
        await db.refresh(transfer)
        await db.refresh(server)
        return transfer