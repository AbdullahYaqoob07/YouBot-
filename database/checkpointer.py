from typing import Optional, AsyncGenerator, Iterator, Sequence, Any
from sqlalchemy import select, desc
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata, CheckpointTuple, WRITES_IDX_MAP
from database.models import get_async_session, LangGraphCheckpoint, LangGraphCheckpointWrite

class AsyncMySQLSaver(BaseCheckpointSaver):
    """Distributed Saver for LangGraph State backed by SQLAlchemy and MySQL."""

    def _serialize_value(self, value: Any) -> tuple[str, bytes]:
        if hasattr(self.serde, "dumps_typed"):
            return self.serde.dumps_typed(value)
        return "json", self.serde.dumps(value)

    def _deserialize_value(self, serialized_type: str, payload: bytes) -> Any:
        if hasattr(self.serde, "loads_typed"):
            return self.serde.loads_typed((serialized_type, payload))
        return self.serde.loads(payload)
    
    async def aget_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"].get("checkpoint_id")
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        
        async with get_async_session() as session:
            query = select(LangGraphCheckpoint).where(LangGraphCheckpoint.thread_id == thread_id)
            if checkpoint_id:
                query = query.where(LangGraphCheckpoint.checkpoint_id == checkpoint_id)
            else:
                query = query.order_by(desc(LangGraphCheckpoint.id)).limit(1)
                
            result = await session.execute(query)
            row = result.scalar_one_or_none()
            if not row:
                return None

            writes_query = select(LangGraphCheckpointWrite).where(
                LangGraphCheckpointWrite.thread_id == thread_id,
                LangGraphCheckpointWrite.checkpoint_id == row.checkpoint_id,
            ).order_by(LangGraphCheckpointWrite.task_id, LangGraphCheckpointWrite.idx)
            writes_result = await session.execute(writes_query)
            pending_writes = [
                (write.task_id, write.channel, self._deserialize_value(write.value_type, write.value_blob))
                for write in writes_result.scalars().all()
            ]
                
            return CheckpointTuple(
                config={"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": row.checkpoint_id}},
                checkpoint=self.serde.loads_typed((self.serde.dumps_typed({})[0], row.checkpoint_blob)) if hasattr(self.serde, 'loads_typed') else self.serde.loads(row.checkpoint_blob),
                metadata=self.serde.loads_typed((self.serde.dumps_typed({})[0], row.metadata_blob)) if hasattr(self.serde, 'loads_typed') else self.serde.loads(row.metadata_blob),
                parent_config={"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": row.parent_checkpoint_id}} if row.parent_checkpoint_id else None,
                pending_writes=pending_writes or None,
            )

    async def aput(self, config: dict, checkpoint: Checkpoint, metadata: CheckpointMetadata, new_versions: dict) -> dict:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = checkpoint["id"]
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")
        
        async with get_async_session() as session:
            new_row = LangGraphCheckpoint(
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                parent_checkpoint_id=parent_checkpoint_id,
                checkpoint_blob=self.serde.dumps_typed(checkpoint)[1] if hasattr(self.serde, 'dumps_typed') else self.serde.dumps(checkpoint),
                metadata_blob=self.serde.dumps_typed(metadata)[1] if hasattr(self.serde, 'dumps_typed') else self.serde.dumps(metadata)
            )
            session.add(new_row)
            await session.commit()
            
        return {"configurable": {"thread_id": thread_id, "checkpoint_ns": config["configurable"].get("checkpoint_ns", ""), "checkpoint_id": checkpoint_id}}

    async def aput_writes(
        self,
        config: dict,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"]["checkpoint_id"]

        async with get_async_session() as session:
            for idx, (channel, value) in enumerate(writes):
                value_type, value_blob = self._serialize_value(value)
                session.add(
                    LangGraphCheckpointWrite(
                        thread_id=thread_id,
                        checkpoint_id=checkpoint_id,
                        task_id=task_id,
                        idx=WRITES_IDX_MAP.get(channel, idx),
                        channel=channel,
                        value_type=value_type,
                        value_blob=value_blob,
                    )
                )
            await session.commit()

    async def asearch(self, config: Optional[dict] = None, *args, **kwargs) -> AsyncGenerator[CheckpointTuple, None]:
        # Minimal implementation required by ABC interface
        thread_id = config.get("configurable", {}).get("thread_id") if config else None
        if not thread_id:
            return
            
        async with get_async_session() as session:
            query = select(LangGraphCheckpoint).where(LangGraphCheckpoint.thread_id == thread_id).order_by(desc(LangGraphCheckpoint.id))
            result = await session.execute(query)
            rows = result.scalars().all()
            for row in rows:
                yield CheckpointTuple(
                    config={"configurable": {"thread_id": thread_id, "checkpoint_id": row.checkpoint_id}},
                    checkpoint=self.serde.loads_typed((self.serde.dumps_typed({})[0], row.checkpoint_blob)) if hasattr(self.serde, 'loads_typed') else self.serde.loads(row.checkpoint_blob),
                    metadata=self.serde.loads_typed((self.serde.dumps_typed({})[0], row.metadata_blob)) if hasattr(self.serde, 'loads_typed') else self.serde.loads(row.metadata_blob),
                    parent_config={"configurable": {"thread_id": thread_id, "checkpoint_id": row.parent_checkpoint_id}} if row.parent_checkpoint_id else None
                )
    
    # Empty sync wrappers to satisfy generic interface bounds
    def get_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        raise NotImplementedError("Use async aget_tuple")

    def put(self, config: dict, checkpoint: Checkpoint, metadata: CheckpointMetadata, new_versions: dict) -> dict:
        raise NotImplementedError("Use async aput")

    def search(self, config: Optional[dict] = None, *args, **kwargs) -> Iterator[CheckpointTuple]:
        raise NotImplementedError("Use async asearch")
