"""Plugin to automatically close orphaned transactions."""

from datetime import UTC, datetime

from .base import ChargePointPlugin, PluginContext, PluginHook


class OrphanedTransactionPlugin(ChargePointPlugin):
    """
    Automatically closes orphaned (unclosed) transactions.

    This plugin monitors:
    - StartTransaction: Closes any orphaned transactions before starting a new one
    - BootNotification: Closes any orphaned transactions when a charger reboots
      (treats boot as implicit transaction stop)

    When orphaned transactions are found, they are closed using:
    - The last meter value recorded for that transaction as the meter_stop
    - "Other" as the stop reason
    - Current timestamp as the stop time

    Use case: Handles edge cases where transactions weren't properly closed due to
    communication failures, power loss, charger reboots, or other anomalies.
    """

    def hooks(self) -> dict[PluginHook, str]:
        """Register hooks to monitor transaction starts and boot notifications."""
        return {
            PluginHook.BEFORE_START_TRANSACTION: "on_before_start_transaction",
            PluginHook.ON_BOOT_NOTIFICATION: "on_boot_notification",
        }

    async def _close_orphaned_transactions(self, context: PluginContext, reason: str = "Other"):
        """
        Close any orphaned (active) transactions for the charge point.

        Args:
            context: Plugin context with charge point info
            reason: Stop reason to use (default: "Other")
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
                    stop_reason=reason,
                )

                self.logger.info(
                    f"Closed orphaned transaction {tx.id} for {cp_id} "
                    f"(reason: {reason}, meter_stop: {meter_stop})"
                )

            except Exception as e:
                self.logger.error(
                    f"Failed to close orphaned transaction {tx.id} for {cp_id}: {e}",
                    exc_info=True,
                )

    async def on_before_start_transaction(self, context: PluginContext):
        """
        Check for and close any orphaned transactions before starting a new one.

        This runs BEFORE the standard StartTransaction handler, ensuring orphaned
        transactions are cleaned up first.
        """
        await self._close_orphaned_transactions(context, reason="Other")

    async def on_boot_notification(self, context: PluginContext):
        """
        Close any orphaned transactions when a charger boots/reboots.

        A boot notification indicates the charger has restarted, so any active
        transactions should be considered terminated. This treats the boot as
        an implicit transaction stop.
        """
        await self._close_orphaned_transactions(context, reason="Reboot")
