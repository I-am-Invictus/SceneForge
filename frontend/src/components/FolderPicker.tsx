import type { Folder } from '../types/assets'

interface FolderPickerProps {
  folders: Folder[]
  value: number | null
  onChange: (folderId: number | null) => void
}

export function FolderPicker({ folders, value, onChange }: FolderPickerProps) {
  const childrenOf = (parentId: number | null): Folder[] =>
    folders
      .filter((f) => f.parent_id === parentId)
      .sort((a, b) => a.name.localeCompare(b.name))

  const renderLevel = (parentId: number | null, depth: number) => (
    <>
      {childrenOf(parentId).map((folder) => (
        <div key={folder.id}>
          <label
            className={`folder-option ${value === folder.id ? 'selected' : ''}`}
            style={{ paddingLeft: 12 + depth * 16 }}
          >
            <input
              type="radio"
              name="folder-picker"
              checked={value === folder.id}
              onChange={() => onChange(folder.id)}
            />
            {folder.name}
          </label>
          {renderLevel(folder.id, depth + 1)}
        </div>
      ))}
    </>
  )

  return (
    <div className="folder-picker">
      <label
        className={`folder-option ${value === null ? 'selected' : ''}`}
        style={{ paddingLeft: 12 }}
      >
        <input
          type="radio"
          name="folder-picker"
          checked={value === null}
          onChange={() => onChange(null)}
        />
        Root
      </label>
      {renderLevel(null, 1)}
    </div>
  )
}
