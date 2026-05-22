type Props = {
  className?: string
  size?: number
}

/** Outline mic icon (capsule + stand arc), matches Claude-style voice button */
export const MicIcon = ({ className = '', size = 18 }: Props) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    aria-hidden
  >
    <rect
      x="9"
      y="3"
      width="6"
      height="10"
      rx="3"
      stroke="currentColor"
      strokeWidth="1.75"
    />
    <path
      d="M6 11.5a6 6 0 0 0 12 0"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
    />
    <path
      d="M12 17.5v3"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
    />
  </svg>
)
