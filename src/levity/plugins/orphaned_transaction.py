"""Plugin to automatically close orphaned transactions."""

from datetime import UTC, datetime

from .base import ChargePointPlugin, PluginContext, PluginHook


class OrphanedTransactionPlugin(ChargePointPlugin):
    """
    Automatically closes orphaned (unclosed) transactions when a new transaction starts.

    This plugin monitors StartTransaction messages. When a new transaction begins,
    it checks if there are any other active transactions for the same charge point.
    If found, it closes them out using:
    - The last meter value recorded for that transaction as the meter_stop
    - "Other" as the stop reason
    - Current timestamp as the stop time

    Use case: Handles edge cases where transactions weren't properly closed due to
    communication failures, power loss, or other anomalies.
    """

    def hooks(self) -> dict[PluginHook, str]:
        """Register hook to monitor transaction starts."""
        return {
            PluginHook.BEFORE_START_TRANSACTION: "on_before_start_transaction",
        }

    async def on_before_start_transaction(self, context: PluginContext):
        """
        Check for and close any orphaned transactions before starting a new one.

        This runs BEFORE the standard StartTransaction handler, ensuring orphaned
        transactions are cleaned up first.
        """
        cp_id = context.charge_point.id
        tx_repo = context.charge_point.tx_repo
        meter_repo = context.charge_point.meter_repo

        # Get all active transactions for this charge point
        active_txs = await tx_repo.get_all_active_for_cp(cp_id)

        if not active_txs:
            return

        # Close each orphaned transaction
        for tx in active_txs:
            try:
                # Get the last meter value for this transaction
                last_meter = await meter_repo.get_last_for_transaction(tx.id)

                if last_meter:
                    meter_stop = int(last_meter.value)
                else:
                    # No meter values recorded - use the meter_start value
                    meter_stop = tx.meter_start
                    self.logger.warning(
                        f"No meter values found for transaction {tx.id}. "
                        f"Using meter_start value {meter_stop}"
                    )

                # Close the transaction
                stop_time = datetime.now(UTC)
                await tx_repo.stop_transaction(
                    tx_db_id=tx.id,
                    stop_time=stop_time,
                    meter_stop=meter_stop,
                    stop_reason="Other",
                )

            except Exception as e:
                self.logger.error(
                    f"Failed to close orphaned transaction {tx.id} for {cp_id}: {e}",
                    exc_info=True,
                )
