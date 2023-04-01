import asyncio
import logging
from asyncio import Event
from typing import AsyncIterator

logger = logging.getLogger(__name__)


async def cancellable_iterator(
    async_iterator: AsyncIterator, cancellation_event: Event
) -> AsyncIterator:
    """Wrap an async iterator such that it exits when the cancellation event is
    set.
    """
    cancellation_task = asyncio.create_task(cancellation_event.wait())
    result_iter = async_iterator.__aiter__()
    iter_next_task = asyncio.create_task(result_iter.__anext__())
    while not cancellation_event.is_set():
        done, pending = await asyncio.wait(
            [cancellation_task, iter_next_task], return_when=asyncio.FIRST_COMPLETED
        )
        for done_task in done:
            if done_task != cancellation_task:
                # We have a result from the async iterator.
                yield done_task.result()
            else:
                logger.info("Cancellation detected")
                # The cancellation token has been set, and we should exit.
                # Cancel any pending tasks. This is safe as there is no await
                # between the completion of the wait on the cancellation event
                # and the pending tasks being cancelled. This means that the
                # pending tasks cannot have done any work.
                for pending_task in pending:
                    pending_task.cancel()
                # Now the tasks are cancelled we can await the cancellation
                # error, knowing they have done no work.
                for pending_task in pending:
                    try:
                        await pending_task
                    except asyncio.CancelledError:
                        pass
