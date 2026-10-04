import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import DOMPurify from "dompurify";
import {
  Archive,
  BookOpen,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  Download,
  Search,
  Expand,
  ExternalLink,
  FlaskConical,
  GitBranch,
  HelpCircle,
  Play,
  RefreshCw,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";

// Only data crosses this protocol; callbacks, run paths and scientific objects stay in Python.
export type ViewNode = {
  id: string;
  type: string;
  children?: ViewNode[];
  [key: string]: any;
};
type Page = { id: string; title: string; group: string; icon: string };
type Snapshot = {
  page: string;
  pages: Page[];
  main: ViewNode[];
  sidebar: ViewNode[];
  revision: number;
  refresh: number | null;
  csrf: string;
};
type Drafts = Record<string, unknown>;
type Runtime = {
  snapshot: Snapshot;
  drafts: Drafts;
  busy: boolean;
  edit: (node: ViewNode, value: unknown, immediate?: boolean) => void;
  commit: (node: ViewNode) => void;
  upload: (node: ViewNode, files: FileList | File[]) => Promise<void>;
};
const Context = createContext<Runtime>(null!);
const useRuntime = () => useContext(Context);
const icons = {
  library: BookOpen,
  science: FlaskConical,
  tree: GitBranch,
  shield: ShieldCheck,
  archive: Archive,
};

function flatten(nodes: ViewNode[]): ViewNode[] {
  return nodes.flatMap((node) => [node, ...flatten(node.children || [])]);
}
function pageFromLocation() {
  return location.pathname.split("/")[1] || "sources";
}
async function readResponse(response: Response): Promise<any> {
  const body = await response.json();
  if (!response.ok)
    throw new Error(
      body.detail || "The server could not complete this request.",
    );
  return body;
}

export function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [drafts, setDrafts] = useState<Drafts>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(() => innerWidth > 1200);
  const viewId = useRef(crypto.randomUUID());
  const current = useRef(snapshot);
  const pending = useRef(drafts);
  const inFlight = useRef(false);
  const queue = useRef(Promise.resolve());
  const mounted = useRef(true);
  const accept = useCallback((next: Snapshot) => {
    if (!mounted.current) return;
    current.current = next;
    setSnapshot(next);
    setUpdatedAt(new Date());
    const path = next.page === "sources" ? "/" : `/${next.page}`;
    if (location.pathname !== path) history.pushState({}, "", path);
  }, []);
  const refresh = useCallback(
    async (page?: string) => {
      if (inFlight.current && !page) return;
      inFlight.current = true;
      // Polls and actions share one queue, so a refresh cannot invalidate a click.
      queue.current = queue.current
        .then(async () => {
          try {
            accept(
              await readResponse(
                await fetch(
                  `/api/view${page ? `?page=${encodeURIComponent(page)}` : ""}`,
                  { headers: { "X-View-ID": viewId.current } },
                ),
              ),
            );
            setError("");
          } catch (e) {
            if (mounted.current) setError(String((e as Error).message));
          }
        })
        .finally(() => {
          inFlight.current = false;
        });
      return queue.current;
    },
    [accept],
  );

  useEffect(() => {
    mounted.current = true;
    void refresh(pageFromLocation());
    const pop = () => void refresh(pageFromLocation());
    window.addEventListener("popstate", pop);
    return () => {
      mounted.current = false;
      window.removeEventListener("popstate", pop);
    };
  }, [refresh]);
  useEffect(() => {
    if (!snapshot?.refresh) return;
    // Snapshots leave local drafts intact. An unfinished form (even on another
    // page) must not stop the live execution feed. The shared queue prevents races.
    const timer = setInterval(() => void refresh(), snapshot.refresh * 1000);
    const catchUp = () => {
      if (!document.hidden) void refresh();
    };
    document.addEventListener("visibilitychange", catchUp);
    window.addEventListener("focus", catchUp);
    window.addEventListener("online", catchUp);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", catchUp);
      window.removeEventListener("focus", catchUp);
      window.removeEventListener("online", catchUp);
    };
  }, [snapshot?.refresh, refresh]);

  const send = (node?: ViewNode, page?: string, explicit?: Drafts) => {
    // Capture intent now, but use the latest revision when its place in the queue runs.
    const view = current.current;
    if (!view) return;
    const controls = flatten([...view.sidebar, ...view.main]);
    const values =
      explicit ??
      Object.fromEntries(
        Object.entries(pending.current).filter(([key]) => {
          const control = controls.find((c) => c.widget === key);
          return control && (!control.form || control.form === node?.form);
        }),
      );
    inFlight.current = true;
    setBusy(true);
    queue.current = queue.current
      .then(async () => {
        try {
          const now = current.current!;
          const response = await readResponse(
            await fetch("/api/event", {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": now.csrf,
                "X-View-ID": viewId.current,
              },
              body: JSON.stringify({
                values,
                page,
                action: node?.type === "button" ? node.widget : null,
                revision: now.revision,
              }),
            }),
          );
          for (const [key, value] of Object.entries(values)) {
            if (pending.current[key] === value) delete pending.current[key];
          }
          pending.current = { ...pending.current };
          setDrafts(pending.current);
          accept(response);
          setError("");
        } catch (e) {
          setError((e as Error).message);
        }
      })
      .finally(() => {
        inFlight.current = false;
        setBusy(false);
      });
  };
  const edit: Runtime["edit"] = (node, value, immediate = false) => {
    pending.current = { ...pending.current, [node.widget]: value };
    setDrafts(pending.current);
    if (immediate && !node.form) send(node);
  };
  const upload: Runtime["upload"] = async (node, files) => {
    setBusy(true);
    inFlight.current = true;
    try {
      const tokens: string[] = [];
      const names: { token: string; name: string }[] = [];
      for (const file of Array.from(files)) {
        if (file.size > 10 * 1024 * 1024)
          throw new Error(`${file.name}: maximum source size is 10 MiB`);
        const result = await readResponse(
          await fetch(
            `/api/upload?widget=${node.widget}&name=${encodeURIComponent(file.name)}`,
            {
              method: "POST",
              headers: {
                "X-CSRF-Token": current.current!.csrf,
                "X-View-ID": viewId.current,
              },
              body: file,
            },
          ),
        );
        tokens.push(result.token);
        names.push(result);
      }
      edit(node, tokens);
      // Names are display-only. The server accepts only its session-bound tokens.
      node.uploadedNames = names;
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      inFlight.current = false;
    }
  };

  if (!snapshot)
    return (
      <main className="loading">
        <div className="brand">
          <b>◈</b> OmniLab
        </div>
        <p role="status">{error || "Loading research workspace…"}</p>
        {error && (
          <button onClick={() => void refresh(pageFromLocation())}>
            Retry connection
          </button>
        )}
      </main>
    );
  const runtime = {
    snapshot,
    drafts,
    busy,
    edit,
    commit: (node: ViewNode) => send(node),
    upload,
  };
  return (
    <Context.Provider value={runtime}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div className={`app-shell ${sidebarOpen ? "with-sidebar" : ""}`}>
        {sidebarOpen && (
          <button
            className="sidebar-scrim"
            aria-label="Close navigation"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <aside
          className="sidebar"
          aria-label="Research navigation"
          hidden={!sidebarOpen}
        >
          <button
            className="icon-button close-sidebar"
            aria-label="Collapse sidebar"
            onClick={() => setSidebarOpen(false)}
          >
            <ChevronsLeft size={20} />
          </button>
          <nav>
            {["Research", "Platform", "Audit"].map((group) => (
              <div className="nav-group" key={group}>
                <div className="nav-group-title">{group}</div>
                {snapshot.pages
                  .filter((p) => p.group === group)
                  .map((page) => {
                    const Icon = icons[page.icon as keyof typeof icons];
                    return (
                      <a
                        href={page.id === "sources" ? "/" : `/${page.id}`}
                        key={page.id}
                        aria-current={
                          snapshot.page === page.id ? "page" : undefined
                        }
                        onClick={(e) => {
                          e.preventDefault();
                          send(undefined, page.id);
                          if (innerWidth <= 800) setSidebarOpen(false);
                        }}
                      >
                        <Icon size={18} />
                        <span>{page.title}</span>
                      </a>
                    );
                  })}
              </div>
            ))}
          </nav>
          <Nodes nodes={snapshot.sidebar} />
        </aside>
        <div className="workspace">
          <header className="app-toolbar">
            {!sidebarOpen && (
              <button
                className="icon-button"
                aria-label="Expand sidebar"
                onClick={() => setSidebarOpen(true)}
              >
                <ChevronsRight size={20} />
              </button>
            )}
            <span className="connection-status" role="status">
              {busy
                ? "Updating…"
                : snapshot.refresh
                  ? error
                    ? "Reconnecting to live updates…"
                    : `Live · updates every ${snapshot.refresh}s`
                  : ""}
              {snapshot.refresh && updatedAt && (
                <time dateTime={updatedAt.toISOString()} aria-live="off">
                  {` · Updated ${updatedAt.toLocaleTimeString()}`}
                </time>
              )}
            </span>
          </header>
          <main id="main" className="block-container" tabIndex={-1}>
            {error && (
              <div className="alert error" role="alert">
                <span>{error}</span>
                <button onClick={() => void refresh()}>Refresh</button>
                <button
                  className="icon-button"
                  onClick={() => setError("")}
                  aria-label="Dismiss error"
                >
                  <X size={16} />
                </button>
              </div>
            )}
            <Nodes nodes={snapshot.main} />
          </main>
        </div>
      </div>
    </Context.Provider>
  );
}

function Nodes({ nodes }: { nodes: ViewNode[] }) {
  return (
    <>
      {nodes.map((node) => (
        <Node key={node.id} node={node} />
      ))}
    </>
  );
}
function RichText({ children }: { children: string }) {
  return (
    <Markdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: (props) => <a {...props} target="_blank" rel="noreferrer" />,
      }}
    >
      {children}
    </Markdown>
  );
}
function Label({ node, children }: { node: ViewNode; children: ReactNode }) {
  return (
    <div className={`field ${node.label_visibility || ""}`}>
      <label htmlFor={node.widget}>
        {node.label}
        {node.help && (
          <span className="help" title={node.help}>
            <HelpCircle size={15} />
          </span>
        )}
      </label>
      {children}
    </div>
  );
}
function Control({ node }: { node: ViewNode }) {
  const { drafts, busy, edit, commit, upload } = useRuntime();
  const value: any = Object.hasOwn(drafts, node.widget)
    ? drafts[node.widget]
    : node.value;
  const disabled = busy || node.disabled;
  if (node.type === "checkbox" || node.type === "toggle")
    return (
      <label className={`check-field ${node.type}`}>
        <input
          type="checkbox"
          role={node.type === "toggle" ? "switch" : undefined}
          checked={!!value}
          disabled={disabled}
          onChange={(e) => edit(node, e.target.checked, true)}
        />
        <span>{node.label}</span>
      </label>
    );
  if (node.type === "button")
    return (
      <button
        type="button"
        className={`button ${node.variant === "primary" ? "primary" : ""} ${node.width === "stretch" ? "stretch" : ""}`}
        disabled={disabled}
        onClick={() => commit(node)}
      >
        {node.icon?.includes("play") && <Play size={16} />}
        {node.icon?.includes("refresh") && <RefreshCw size={16} />}
        {node.label}
      </button>
    );
  if (node.type === "selectbox")
    return (
      <SelectControl
        node={node}
        value={value}
        disabled={disabled}
        onSelect={(index) => edit(node, index, true)}
      />
    );
  if (node.type === "segmented_control" || node.type === "pills")
    return (
      <Label node={node}>
        <div
          role="group"
          aria-label={node.label}
          className={`segments ${node.type}`}
        >
          {node.options.map((option: string, index: number) => (
            <button
              type="button"
              aria-pressed={value === index}
              key={index}
              disabled={disabled}
              onClick={() => edit(node, index, true)}
            >
              {option}
            </button>
          ))}
        </div>
      </Label>
    );
  if (node.type === "file_uploader") {
    const names = node.uploadedNames || node.value || [];
    return (
      <Label node={node}>
        <div
          className="upload-zone"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            if (!disabled) void upload(node, e.dataTransfer.files);
          }}
        >
          <Upload size={24} />
          <div>
            <div>Drag and drop files here</div>
            <small>Limit 10 MiB per file · PDF, MD</small>
          </div>
          <label className="button browse">
            Browse files
            <input
              id={node.widget}
              type="file"
              accept=".pdf,.md"
              multiple
              disabled={disabled}
              onChange={(e) => {
                if (e.target.files) void upload(node, e.target.files);
              }}
            />
          </label>
        </div>
        {names.map((f: any) => (
          <div className="upload-name" key={f.token}>
            {f.name}
          </div>
        ))}
      </Label>
    );
  }
  const numeric = node.type === "number_input";
  return (
    <Label node={node}>
      <input
        id={node.widget}
        type={numeric ? "number" : "text"}
        value={value ?? ""}
        disabled={node.disabled}
        placeholder={node.placeholder}
        min={node.min_value}
        max={node.max_value}
        step={node.step}
        onChange={(e) =>
          edit(
            node,
            numeric && e.target.value !== ""
              ? Number(e.target.value)
              : e.target.value,
          )
        }
        onBlur={() => {
          if (!node.form && Object.hasOwn(drafts, node.widget)) commit(node);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            if (!node.form) commit(node);
            else e.currentTarget.closest("form")?.requestSubmit();
          }
        }}
      />
    </Label>
  );
}

function SelectControl({
  node,
  value,
  disabled,
  onSelect,
}: {
  node: ViewNode;
  value: number | null;
  disabled: boolean;
  onSelect: (index: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [position, setPosition] = useState({
    left: 0,
    top: 0,
    width: 0,
    maxHeight: 280,
  });
  const ref = useRef<HTMLInputElement>(null);
  const popup = useRef<HTMLDivElement>(null);
  const options: { label: string; index: number }[] = node.options
    .map((label: string, index: number) => ({ label, index }))
    .filter((o: { label: string }) =>
      o.label.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
    );
  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (
        !ref.current?.contains(e.target as globalThis.Node) &&
        !popup.current?.contains(e.target as globalThis.Node)
      )
        setOpen(false);
    };
    const positionMenu = () => {
      const r = ref.current?.getBoundingClientRect();
      if (r) {
        const below = innerHeight - r.bottom - 12;
        const above = r.top - 12;
        const opensBelow = below >= 160 || below >= above;
        const maxHeight = Math.min(
          280,
          Math.max(80, opensBelow ? below : above),
        );
        setPosition({
          left: r.left,
          top: opensBelow ? r.bottom + 4 : Math.max(8, r.top - maxHeight - 4),
          width: r.width,
          maxHeight,
        });
      }
    };
    positionMenu();
    document.addEventListener("pointerdown", close);
    window.addEventListener("resize", positionMenu);
    return () => {
      document.removeEventListener("pointerdown", close);
      window.removeEventListener("resize", positionMenu);
    };
  }, [open]);
  const choose = (index: number) => {
    setOpen(false);
    setQuery("");
    onSelect(index);
  };
  return (
    <Label node={node}>
      <div className="select-wrap">
        <input
          type="text"
          ref={ref}
          id={node.widget}
          role="combobox"
          aria-expanded={open}
          aria-controls={`${node.widget}-options`}
          aria-autocomplete="list"
          aria-activedescendant={
            open && options[active]
              ? `${node.widget}-option-${options[active].index}`
              : undefined
          }
          autoComplete="off"
          disabled={disabled || !node.options.length}
          value={open ? query : node.options[value ?? -1] || ""}
          placeholder={
            node.options[value ?? -1] ||
            node.placeholder ||
            "No options to select"
          }
          onClick={() => {
            setOpen(true);
            setQuery("");
            setActive(0);
          }}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
            setActive(0);
          }}
          onBlur={(e) => {
            if (!popup.current?.contains(e.relatedTarget as globalThis.Node))
              setOpen(false);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setOpen(false);
              setQuery("");
            }
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              setOpen(true);
              setActive(
                Math.max(
                  0,
                  Math.min(
                    options.length - 1,
                    active + (e.key === "ArrowDown" ? 1 : -1),
                  ),
                ),
              );
            }
            if (e.key === "Enter" && open && options[active]) {
              e.preventDefault();
              choose(options[active].index);
            }
          }}
        />
        <ChevronDown size={16} />
      </div>
      {open &&
        createPortal(
          <div
            className="select-menu"
            ref={popup}
            role="listbox"
            id={`${node.widget}-options`}
            aria-label={`${node.label} options`}
            style={position}
          >
            {options.length ? (
              options.map((option, i) => (
                <div
                  key={option.index}
                  id={`${node.widget}-option-${option.index}`}
                  role="option"
                  aria-selected={option.index === value}
                  className={i === active ? "active" : ""}
                  onPointerDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => choose(option.index)}
                >
                  {option.label}
                </div>
              ))
            ) : (
              <div className="caption">No results</div>
            )}
          </div>,
          document.body,
        )}
    </Label>
  );
}

function Tabs({ node }: { node: ViewNode }) {
  const [selected, setSelected] = useState(0);
  return (
    <div className="tabs">
      <div role="tablist">
        {node.labels.map((label: string, i: number) => (
          <button
            key={label}
            role="tab"
            id={`${node.id}-${i}`}
            aria-controls={`${node.id}-panel-${i}`}
            aria-selected={selected === i}
            tabIndex={selected === i ? 0 : -1}
            onClick={() => setSelected(i)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                e.preventDefault();
                const next =
                  (selected +
                    (e.key === "ArrowRight" ? 1 : node.labels.length - 1)) %
                  node.labels.length;
                setSelected(next);
                (
                  e.currentTarget.parentElement?.children[next] as HTMLElement
                ).focus();
              }
            }}
          >
            {label}
          </button>
        ))}
      </div>
      {node.children?.map((child, i) => (
        <div
          role="tabpanel"
          aria-labelledby={`${node.id}-${i}`}
          id={`${node.id}-panel-${i}`}
          key={child.id}
          hidden={i !== selected}
        >
          <Nodes nodes={child.children || []} />
        </div>
      ))}
    </div>
  );
}
function JsonValue({
  value,
  depth = 0,
  expanded = true,
}: {
  value: any;
  depth?: number;
  expanded?: boolean;
}) {
  if (value === null || typeof value !== "object")
    return (
      <span className={`json-primitive ${typeof value}`}>
        {JSON.stringify(value)}
      </span>
    );
  const entries = Object.entries(value);
  return (
    <details
      className="json-value"
      open={(depth === 0 && expanded) || undefined}
    >
      <summary>
        {Array.isArray(value)
          ? `[ ${entries.length} items ]`
          : `{ ${entries.length} keys }`}
      </summary>
      <div className="json-entries">
        {entries.map(([key, child]) => (
          <div key={key}>
            <span className="json-key">{key}: </span>
            <JsonValue value={child} depth={depth + 1} expanded={expanded} />
          </div>
        ))}
      </div>
    </details>
  );
}
function DataTable({ node }: { node: ViewNode }) {
  const [sort, setSort] = useState<{ index: number; direction: number } | null>(
    null,
  );
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const tableRef = useRef<HTMLDivElement>(null);
  const rows = node.rows.filter(
    (row: unknown[]) =>
      !query ||
      row.some((value) =>
        String(value ?? "")
          .toLocaleLowerCase()
          .includes(query.toLocaleLowerCase()),
      ),
  );
  if (sort)
    rows.sort(
      (a: any[], b: any[]) =>
        (typeof a[sort.index] === "number"
          ? a[sort.index] - b[sort.index]
          : String(a[sort.index] ?? "").localeCompare(
              String(b[sort.index] ?? ""),
              undefined,
              { numeric: true },
            )) * sort.direction,
    );
  const csv = () => {
    const content = [node.columns, ...rows]
      .map((row) =>
        row
          .map((v: any) => `"${String(v ?? "").replaceAll('"', '""')}"`)
          .join(","),
      )
      .join("\n");
    const url = URL.createObjectURL(new Blob([content], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "table.csv";
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="table-shell" ref={tableRef}>
      <div className="table-tools">
        {searching && (
          <input
            className="table-search"
            aria-label="Search table"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
        )}
        <button
          className="icon-button"
          aria-label="Search table rows"
          onClick={() => {
            setSearching(!searching);
            setQuery("");
          }}
        >
          <Search size={15} />
        </button>
        <button
          className="icon-button"
          aria-label="View table fullscreen"
          onClick={() => {
            if (document.fullscreenElement) void document.exitFullscreen();
            else void tableRef.current?.requestFullscreen();
          }}
        >
          <Expand size={15} />
        </button>
        <button
          className="icon-button"
          aria-label="Download table as CSV"
          onClick={csv}
        >
          <Download size={15} />
        </button>
      </div>
      <div
        className="table-scroll"
        style={{
          maxHeight: typeof node.height === "number" ? node.height : 400,
        }}
      >
        <table aria-label={node.alt || "Data table"}>
          <thead>
            <tr>
              {node.columns.map((column: string, i: number) => (
                <th
                  key={column}
                  aria-sort={
                    sort?.index === i
                      ? sort.direction === 1
                        ? "ascending"
                        : "descending"
                      : "none"
                  }
                >
                  <button
                    onClick={() =>
                      setSort({
                        index: i,
                        direction: sort?.index === i ? -sort.direction : 1,
                      })
                    }
                  >
                    {column}
                    {sort?.index === i
                      ? sort.direction === 1
                        ? " ↑"
                        : " ↓"
                      : ""}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row: any[], i: number) => (
              <tr key={i}>
                {row.map((value, j) => (
                  <td key={j}>
                    {value === null
                      ? "—"
                      : typeof value === "object"
                        ? JSON.stringify(value)
                        : typeof value === "number" &&
                            node.column_config?.[node.columns[j]]?.format ===
                              "percent"
                          ? `${(value * 100).toFixed(2)}%`
                          : String(value)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!rows.length && <p className="caption">No rows</p>}
    </div>
  );
}
function Chart({ node }: { node: ViewNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  const spec = JSON.stringify(node.spec);
  useEffect(() => {
    let disposed = false;
    let cleanup: (() => void) | undefined;
    import("vega-embed")
      .then(async ({ default: embed }) => {
        if (disposed || !ref.current) return;
        const result = await embed(ref.current, JSON.parse(spec), {
          actions: {
            export: true,
            source: false,
            compiled: false,
            editor: false,
          },
          renderer: "svg",
        });
        cleanup = () => result.finalize();
        if (disposed) cleanup();
      })
      .catch((e) => setError(e.message));
    return () => {
      disposed = true;
      cleanup?.();
    };
  }, [spec]);
  return (
    <div className="chart" role="img" aria-label={node.alt} ref={ref}>
      {error && <div className="alert error">{error}</div>}
    </div>
  );
}
let vizPromise: Promise<any> | undefined;
function Graphviz({ node }: { node: ViewNode }) {
  const [svg, setSvg] = useState("");
  useEffect(() => {
    let cancelled = false;
    vizPromise ||= import("@viz-js/viz").then((m) => m.instance());
    vizPromise
      .then((viz) => {
        if (!cancelled) setSvg(viz.renderString(node.dot, { format: "svg" }));
      })
      .catch(() => {
        if (!cancelled) setSvg("");
      });
    return () => {
      cancelled = true;
    };
  }, [node.dot]);
  return (
    <div
      className="graphviz"
      role="img"
      aria-label={node.alt}
      dangerouslySetInnerHTML={{
        __html: DOMPurify.sanitize(svg, {
          USE_PROFILES: { svg: true, svgFilters: true },
        }),
      }}
    />
  );
}
function ExecutionGraph({ node }: { node: ViewNode }) {
  const { edit } = useRuntime();
  const ref = useRef<HTMLDivElement>(null);
  const focusKey = useRef<string | null>(null);
  useEffect(() => {
    const boxes = ref.current?.querySelectorAll<SVGElement>(
      "[data-activity-key]",
    );
    boxes?.forEach((box) => {
      const key = box.dataset.activityKey!;
      if (key === focusKey.current) {
        box.focus({ preventScroll: true });
        focusKey.current = null;
      }
      box.setAttribute("role", "button");
      box.setAttribute("tabindex", "0");
      box.setAttribute("aria-label", node.graph.labels[key]);
      box.setAttribute("aria-pressed", String(key === node.graph.selected));
      if (node.graph.follow && key === node.graph.selected && ref.current)
        ref.current.scrollTop =
          box.getBoundingClientRect().top -
          ref.current.getBoundingClientRect().top +
          ref.current.scrollTop -
          ref.current.clientHeight / 2;
    });
  }, [node.graph.svg, node.graph.selected, node.graph.follow]);
  const select = (target: EventTarget) => {
    const box = (target as Element).closest("[data-activity-key]");
    if (box) {
      focusKey.current = box.getAttribute("data-activity-key");
      edit(node, focusKey.current, true);
    }
  };
  return (
    <div
      className="execution-graph"
      ref={ref}
      onClick={(e) => select(e.target)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          select(e.target);
        }
      }}
      dangerouslySetInnerHTML={{
        __html: DOMPurify.sanitize(node.graph.svg, {
          USE_PROFILES: { svg: true, svgFilters: true },
        }),
      }}
    />
  );
}
function ProcessFrame({ node }: { node: ViewNode }) {
  const ref = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(
    typeof node.height === "number" ? node.height : 650,
  );
  useEffect(() => {
    const resize = (event: MessageEvent) => {
      if (
        event.source === ref.current?.contentWindow &&
        event.data?.type === "omnigent-player-height" &&
        Number.isFinite(event.data.height)
      )
        setHeight(Math.min(2400, Math.max(240, event.data.height)));
    };
    window.addEventListener("message", resize);
    return () => window.removeEventListener("message", resize);
  }, []);
  return (
    <iframe
      ref={ref}
      className="process-frame"
      title={node.alt || "Simulation player"}
      src={node.url}
      sandbox="allow-scripts"
      style={{ height }}
    />
  );
}

function Node({ node }: { node: ViewNode }): ReactNode {
  const runtime = useRuntime();
  if (
    [
      "selectbox",
      "segmented_control",
      "pills",
      "number_input",
      "text_input",
      "checkbox",
      "toggle",
      "button",
      "file_uploader",
    ].includes(node.type)
  )
    return <Control node={node} />;
  const children = <Nodes nodes={node.children || []} />;
  switch (node.type) {
    case "title":
      return <h1>{node.value}</h1>;
    case "header":
      return <h2>{node.value}</h2>;
    case "subheader":
      return <h3>{node.value}</h3>;
    case "caption":
      return (
        <div className="caption">
          <RichText>{node.value}</RichText>
        </div>
      );
    case "markdown":
      return (
        <div className="markdown">
          <RichText>{node.value}</RichText>
        </div>
      );
    case "text":
      return <div className="plain-text">{node.value}</div>;
    case "html":
      return (
        <div
          dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(node.value) }}
        />
      );
    case "info":
    case "warning":
    case "error":
    case "success":
      return (
        <div
          className={`alert ${node.type}`}
          role={node.type === "error" ? "alert" : "status"}
        >
          <RichText>{node.value}</RichText>
        </div>
      );
    case "container":
      return (
        <div
          className={`container ${node.border ? "bordered" : ""} ${node.horizontal ? "horizontal" : ""}`}
        >
          {children}
        </div>
      );
    case "columns":
      return (
        <div
          className={`columns ${node.gap || ""}`}
          style={{
            gridTemplateColumns: node.weights
              .map((w: number) => `minmax(0, ${w}fr)`)
              .join(" "),
          }}
        >
          {children}
        </div>
      );
    case "column":
    case "root":
      return <div className="column">{children}</div>;
    case "expander":
      return <Disclosure node={node}>{children}</Disclosure>;
    case "tabs":
      return <Tabs node={node} />;
    case "form":
      return (
        <form
          className="view-form"
          onSubmit={(e) => {
            e.preventDefault();
            const submit = flatten(node.children || []).find(
              (n) => n.type === "button",
            );
            if (submit) runtime.commit(submit);
          }}
        >
          {children}
        </form>
      );
    case "divider":
      return <hr />;
    case "metric":
      return (
        <div className="metric">
          <div className="metric-label">{node.label}</div>
          <div className="metric-value">{node.value}</div>
          {node.delta != null && <div>{node.delta}</div>}
        </div>
      );
    case "json":
      return (
        <div className="json">
          <JsonValue value={node.value} expanded={node.expanded} />
        </div>
      );
    case "code":
      return <Code node={node} />;
    case "dataframe":
      return <DataTable node={node} />;
    case "chart":
      return <Chart node={node} />;
    case "graphviz":
      return <Graphviz node={node} />;
    case "execution_graph":
      return <ExecutionGraph node={node} />;
    case "iframe":
      return <ProcessFrame node={node} />;
    case "image":
      return (
        <img className="visualization" src={node.url} alt={node.alt || ""} />
      );
    case "download":
      return (
        <a
          className={`button ${node.width === "stretch" ? "stretch" : ""}`}
          href={node.url}
          download={node.filename}
        >
          <Download size={15} />
          {node.label}
        </a>
      );
    case "link":
      return /^(https?:)\/\//.test(node.url) ? (
        <a className="button" href={node.url} target="_blank" rel="noreferrer">
          <ExternalLink size={15} />
          {node.label}
        </a>
      ) : null;
    default:
      return (
        <div className="alert error">
          Unsupported view component: {node.type}
        </div>
      );
  }
}
function Disclosure({
  node,
  children,
}: {
  node: ViewNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(!!node.expanded);
  return (
    <details
      className="expander"
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>
        <ChevronDown size={16} />
        {node.label}
      </summary>
      <div className="expander-content">{children}</div>
    </details>
  );
}
function Code({ node }: { node: ViewNode }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="code-shell">
      <button
        className="copy-button"
        onClick={async () => {
          await navigator.clipboard.writeText(node.value);
          setCopied(true);
        }}
      >
        {copied ? "Copied" : "Copy"}
      </button>
      <pre
        style={{
          maxHeight: node.height || 480,
          whiteSpace: node.wrap_lines ? "pre-wrap" : "pre",
        }}
      >
        <code>{node.value}</code>
      </pre>
    </div>
  );
}
