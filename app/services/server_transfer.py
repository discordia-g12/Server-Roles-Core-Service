import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BadRequestError, ForbiddenError, NotFoundError, ServerNotFoundError
from app.models.server_ownership_transfer import ServerOwnershipTransfer
from app.repositories.server_transfer import ServerTransferRepository


class ServerTransferService:
    def __init__(self, repo: ServerTransferRepository | None = None):
        self.repo = repo or ServerTransferRepository()

    async def initiate_transfer(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        owner_id: str,
        target_user_id: str,
    ) -> ServerOwnershipTransfer:
        server = await self.repo.get_server(db, server_id)
        if not server:
            raise ServerNotFoundError()

        if server.owner_id != owner_id:
            raise ForbiddenError("Only the server owner can initiate an ownership transfer.")

        if target_user_id == owner_id:
            raise BadRequestError("Cannot transfer ownership to yourself.")

        is_member = await self.repo.is_member(db, server_id, target_user_id)
        if not is_member:
            raise BadRequestError("Target user is not a member of this server.")

        await self.repo.cancel_pending_transfers(db, server_id)

        transfer = ServerOwnershipTransfer(
            server_id=server_id,
            sender_id=owner_id,
            target_user_id=target_user_id,
            status="PENDING",
        )
        return await self.repo.create_transfer(db, transfer)

    async def accept_transfer(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        user_id: str,
        transfer_id: uuid.UUID | None = None,
    ) -> ServerOwnershipTransfer:
        if transfer_id:
            transfer = await self.repo.get_transfer_by_id(db, transfer_id)
            if not transfer or transfer.server_id != server_id:
                raise NotFoundError("Ownership transfer request not found.")
        else:
            transfer = await self.repo.get_pending_transfer_for_user(db, server_id, user_id)
            if not transfer:
                raise NotFoundError("No pending ownership transfer request found for you.")

        if transfer.target_user_id != user_id:
            raise ForbiddenError("Only the transfer recipient can accept the ownership transfer.")

        if transfer.status != "PENDING":
            raise BadRequestError(f"Transfer cannot be accepted because its status is {transfer.status}.")

        server = await self.repo.get_server(db, server_id)
        if not server:
            raise ServerNotFoundError()

        is_member = await self.repo.is_member(db, server_id, user_id)
        if not is_member:
            raise BadRequestError("You are not a member of this server.")


        return await self.repo.complete_ownership_transfer(
            db, server=server, transfer=transfer, new_owner_id=user_id
        )

    async def reject_transfer(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        user_id: str,
        transfer_id: uuid.UUID | None = None,
    ) -> ServerOwnershipTransfer:
        if transfer_id:
            transfer = await self.repo.get_transfer_by_id(db, transfer_id)
            if not transfer or transfer.server_id != server_id:
                raise NotFoundError("Ownership transfer request not found.")
        else:
            transfer = await self.repo.get_pending_transfer_for_user(db, server_id, user_id)
            if not transfer:
                raise NotFoundError("No pending ownership transfer request found for you.")

        if transfer.target_user_id != user_id:
            raise ForbiddenError("Only the transfer recipient can reject the ownership transfer.")

        if transfer.status != "PENDING":
            raise BadRequestError(f"Transfer cannot be rejected because its status is {transfer.status}.")

        return await self.repo.update_transfer_status(db, transfer, status="REJECTED")

    async def cancel_transfer(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        user_id: str,
        transfer_id: uuid.UUID,
    ) -> ServerOwnershipTransfer:
        transfer = await self.repo.get_transfer_by_id(db, transfer_id)
        if not transfer or transfer.server_id != server_id:
            raise NotFoundError("Ownership transfer request not found.")

        server = await self.repo.get_server(db, server_id)
        if not server:
            raise ServerNotFoundError()

        if server.owner_id != user_id and transfer.sender_id != user_id:
            raise ForbiddenError("Only the server owner can cancel the ownership transfer.")

        if transfer.status != "PENDING":
            raise BadRequestError(f"Transfer cannot be cancelled because its status is {transfer.status}.")

        return await self.repo.update_transfer_status(db, transfer, status="CANCELLED")

    async def get_pending_transfer(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        user_id: str,
    ) -> ServerOwnershipTransfer | None:
        server = await self.repo.get_server(db, server_id)
        if not server:
            raise ServerNotFoundError()

        is_member = await self.repo.is_member(db, server_id, user_id)
        if not is_member:
            raise ForbiddenError("You must be a member of the server to view transfers.")

        return await self.repo.get_pending_transfer_for_server(db, server_id)