import type { SVGProps } from 'react'

const PATHS: Record<string, string> = {
  generate: 'M4 5h12M4 9h12M4 13h8 M15 15l2 2 3-3',
  modify: 'M5 16l8.5-8.5 3 3L8 19H5v-3zM12 6.5l1.8-1.8 3 3-1.8 1.8',
  swap: 'M4 7h11l-2.5-2.5M20 13H9l2.5 2.5',
  characters: 'M8 10a3 3 0 100-6 3 3 0 000 6zM3 18c0-2.8 2.2-5 5-5s5 2.2 5 5',
  scenes: 'M4 5h12v10H4zM4 12l4-3 3 2 3-4 2 2.5M8 12l1.5 3',
  star: 'M9 3l2 4.1 4.5.7-3.2 3.2.7 4.5L9 13.5 4.9 15.5l.8-4.5L2.5 7.8 7 7.1z',
  galleries: 'M3 3h5v5H3zM10 3h5v5h-5zM3 10h5v5H3zM10 10h5v5h-5z',
  history: 'M9 4a5 5 0 11-4.9 6M9 4V1.5M9 4H6.5M9 8v3l2.5 1.5',
  workflows: 'M3 4h4v4H3zM12 12h4v4h-4zM7 6h3a2 2 0 012 2v2M14 14v-2a2 2 0 00-2-2H9',
  settings: 'M9 6.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM9 16.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM2.5 9h3M12.5 9h3M4.5 4.5L6 6M12 12l1.5 1.5M4.5 13.5L6 12M12 6l1.5-1.5',
  menu: 'M3 5h12M3 9h12M3 13h12',
  close: 'M5 5l8 8M13 5l-8 8',
  trash: 'M4.5 6h9M7 6V4.5a1 1 0 011-1h2a1 1 0 011 1V6M6 6l.4 8.1a1 1 0 001 .9h3.2a1 1 0 001-.9L12 6M7.8 8.5v3.5M10.2 8.5v3.5',
  moveToLibrary: 'M3 8h4l1.5 1.5H15V16H3zM9 2v4.5M6.8 4.3 9 6.5l2.2-2.2',
  developer: 'M4 6l3 3-3 3M9 12h5',
}

export type IconName = keyof typeof PATHS

interface IconProps extends SVGProps<SVGSVGElement> {
  name: IconName
  size?: number
}

export function Icon({ name, size = 18, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 18 18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      <path d={PATHS[name]} />
    </svg>
  )
}
