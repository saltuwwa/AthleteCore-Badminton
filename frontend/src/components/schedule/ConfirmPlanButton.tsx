export const ConfirmPlanButton = ({
  onClick,
  disabled,
}: {
  onClick: () => void
  disabled?: boolean
}) => {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="font-mono-ui mt-3 w-full rounded-lg border border-[rgba(200,255,95,0.2)] bg-[rgba(200,255,95,0.1)] px-3 py-2 text-[11px] text-[var(--accent)] transition hover:scale-[1.02] disabled:opacity-60"
    >
      {disabled ? 'Confirming...' : 'Confirm Plan'}
    </button>
  )
}
