import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useDebouncedSearch } from "../lib/useDebouncedSearch";
import { TextField } from "./TextField";

interface SearchComboboxProps<T> {
  id?: string;
  search: (query: string) => Promise<T[]>;
  // See useDebouncedSearch's dependencyKey.
  dependencyKey?: string;
  itemKey: (item: T) => string | number;
  renderItem: (item: T) => ReactNode;
  onPick: (item: T) => void;
  // Shorter queries don't search. 0 searches as soon as the field is focused, empty or not.
  minChars?: number;
  // A picked item shown in the field: no search runs until the field is edited, which calls
  // onEdit (to drop the pick). Leave unset to empty the field after each pick instead.
  selectedLabel?: string | null;
  onEdit?: () => void;
  // Shown when nothing matches; a function gets the trimmed query.
  emptyText: string | ((query: string) => string);
  // Above the results when the field is empty (minChars 0).
  emptyQueryHeading?: string;
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
  disabled?: boolean;
}

// A live-search field with its list of matches: mouse, or ↑/↓ then Enter, picks one; Escape
// closes the list. Searches once typing pauses (useDebouncedSearch).
export function SearchCombobox<T>({
  id,
  search,
  dependencyKey,
  itemKey,
  renderItem,
  onPick,
  minChars = 2,
  selectedLabel,
  onEdit,
  emptyText,
  emptyQueryHeading,
  placeholder,
  ariaLabel,
  className,
  disabled = false,
}: SearchComboboxProps<T>) {
  const [query, setQuery] = useState(selectedLabel ?? "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => {
    if (selectedLabel !== undefined) setQuery(selectedLabel ?? "");
  }, [selectedLabel]);

  const searchable = !selectedLabel && query.trim().length >= minChars;
  const { results, loading, error } = useDebouncedSearch(query.trim(), search, {
    enabled: open && searchable && !disabled,
    dependencyKey,
  });

  useEffect(() => setActive(0), [results]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function handleInputChange(value: string) {
    setQuery(value);
    setOpen(true);
    if (selectedLabel) onEdit?.();
  }

  function pick(item: T) {
    onPick(item);
    setOpen(false);
    if (selectedLabel === undefined) setQuery("");
  }

  const showDropdown = open && searchable && !disabled;
  const hasResults = showDropdown && !loading && !error && results.length > 0;

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      if (hasResults) setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (hasResults) setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      if (hasResults && results[active] !== undefined) {
        event.preventDefault();
        pick(results[active]);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const optionId = (i: number) => `${listId}-option-${i}`;

  return (
    <div ref={containerRef} className={cn("relative w-full max-w-sm", className)}>
      <TextField
        id={id}
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={showDropdown}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={hasResults ? optionId(active) : undefined}
        value={query}
        disabled={disabled}
        onChange={(e) => handleInputChange(e.target.value)}
        onFocus={() => setOpen(true)}
        // A pick keeps focus in the field (see the options' onMouseDown): a click must reopen.
        onClick={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        autoComplete="off"
      />
      {showDropdown && (
        <div className="absolute z-20 mt-1 max-h-80 w-full overflow-y-auto rounded-lg border border-border bg-card shadow-md">
          {loading && <p className="px-3 py-2 text-sm text-muted-foreground">Recherche...</p>}
          {!loading && error && <p className="px-3 py-2 text-sm text-destructive">{error}</p>}
          {!loading && !error && results.length === 0 && (
            <p className="px-3 py-2 text-sm text-muted-foreground">
              {typeof emptyText === "function" ? emptyText(query.trim()) : emptyText}
            </p>
          )}
          {hasResults && !query.trim() && emptyQueryHeading && (
            <p className="px-3 pt-2 pb-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              {emptyQueryHeading}
            </p>
          )}
          <ul id={listId} role="listbox" className="m-0 list-none p-0">
            {hasResults &&
              results.map((item, i) => (
                <li
                  key={itemKey(item)}
                  id={optionId(i)}
                  role="option"
                  aria-selected={i === active}
                  className={cn(
                    "block w-full cursor-pointer px-3 py-2 text-left text-sm",
                    i === active && "bg-[color:var(--color-primary-tint)]",
                  )}
                  // Keeps focus in the field, so ↑/↓ and further typing still work after a click.
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => pick(item)}
                >
                  {renderItem(item)}
                </li>
              ))}
          </ul>
        </div>
      )}
    </div>
  );
}
