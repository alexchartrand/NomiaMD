import { useEffect, useMemo, useRef, useState } from "react";
import { KeyRound, LogOut, Pencil, UserCheck, UserPlus, UserX, Users } from "lucide-react";
import { toast } from "sonner";
import {
  createAdminUser,
  deactivateAdminUser,
  describeError,
  listAdminUsers,
  reactivateAdminUser,
  resetAdminUserPassword,
  revokeAdminUserSessions,
  updateAdminUser,
  type AdminUser,
  type TemporaryPassword,
} from "../../../api";
import { useAuth } from "../../../AuthContext";
import {
  Badge,
  Banner,
  Button,
  EmptyState,
  FilterField,
  Pagination,
  RowActions,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TextField,
  useConfirm,
  type RowAction,
} from "../../../components";
import { usePagination } from "../../../lib/usePagination";
import { formatCount, formatDateTime, ROLE_LABELS } from "./format";
import { TemporaryPasswordModal } from "./TemporaryPasswordModal";
import { UserFormModal } from "./UserFormModal";

function matches(user: AdminUser, search: string): boolean {
  const needle = search.trim().toLowerCase();
  if (!needle) return true;
  return [user.full_name, user.email, user.practice_number ?? ""].some((value) => value.toLowerCase().includes(needle));
}

// Every account: who they are, whether they can log in, how much work hangs off them, and
// what an admin can do about it. Accounts are deactivated, never deleted.
export function UsersTab() {
  const { user: me } = useAuth();
  const { confirm, dialog } = useConfirm();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<AdminUser | "new" | null>(null);
  const [issued, setIssued] = useState<TemporaryPassword | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    listAdminUsers()
      .then(setUsers)
      .catch((err) => setError(describeError(err)))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  const shown = useMemo(() => users.filter((user) => matches(user, search)), [users, search]);
  const pages = usePagination(shown, search);
  const listRef = useRef<HTMLDivElement>(null);

  function replace(updated: AdminUser) {
    setUsers((current) => current.map((user) => (user.id === updated.id ? updated : user)));
  }

  async function run(action: () => Promise<void>) {
    try {
      await action();
    } catch (err) {
      toast.error(describeError(err));
    }
  }

  async function handleDeactivate(user: AdminUser) {
    const ok = await confirm({
      title: `Désactiver ${user.full_name} ?`,
      message: "Le compte ne pourra plus se connecter et ses sessions ouvertes seront fermées. Son historique est conservé ; vous pourrez le réactiver.",
      confirmLabel: "Désactiver",
      tone: "danger",
    });
    if (ok) await run(async () => {
      replace(await deactivateAdminUser(user.id));
      toast.success(`${user.full_name} est désactivé.`);
    });
  }

  async function handleReset(user: AdminUser) {
    const ok = await confirm({
      title: `Réinitialiser le mot de passe de ${user.full_name} ?`,
      message: "Un mot de passe temporaire remplacera l'actuel, et toutes ses sessions seront fermées.",
      confirmLabel: "Réinitialiser",
    });
    if (ok) await run(async () => {
      const result = await resetAdminUserPassword(user.id);
      replace(result.user);
      setIssued(result);
    });
  }

  async function handleRevoke(user: AdminUser) {
    const ok = await confirm({
      title: `Déconnecter ${user.full_name} partout ?`,
      message: "Toutes ses sessions ouvertes seront fermées. Il pourra se reconnecter avec son mot de passe.",
      confirmLabel: "Déconnecter",
    });
    if (ok) await run(async () => {
      await revokeAdminUserSessions(user.id);
      toast.success(`Sessions de ${user.full_name} fermées.`);
    });
  }

  function actionsFor(user: AdminUser): RowAction[] {
    const self = user.id === me?.id;
    return [
      { label: "Modifier", icon: Pencil, onSelect: () => setEditing(user) },
      { label: "Réinitialiser le mot de passe", icon: KeyRound, onSelect: () => handleReset(user), disabled: self },
      { label: "Déconnecter partout", icon: LogOut, onSelect: () => handleRevoke(user), disabled: self || !user.is_active },
      {
        label: "Réactiver",
        icon: UserCheck,
        onSelect: () => run(async () => replace(await reactivateAdminUser(user.id))),
        disabled: user.is_active,
      },
      { label: "Désactiver", icon: UserX, danger: true, onSelect: () => handleDeactivate(user), disabled: self || !user.is_active },
    ];
  }

  async function handleSubmit(fields: Parameters<typeof createAdminUser>[0]) {
    if (editing === "new") {
      const result = await createAdminUser(fields);
      setUsers((current) => [...current, result.user].sort((a, b) => a.full_name.localeCompare(b.full_name)));
      setEditing(null);
      setIssued(result);
    } else if (editing) {
      const { email: _email, ...editable } = fields;
      replace(await updateAdminUser(editing.id, editable));
      setEditing(null);
      toast.success("Compte enregistré.");
    }
  }

  return (
    <>
      {dialog}
      {editing && (
        <UserFormModal user={editing === "new" ? undefined : editing} onSubmit={handleSubmit} onClose={() => setEditing(null)} />
      )}
      {issued && <TemporaryPasswordModal issued={issued} onClose={() => setIssued(null)} />}

      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
        <FilterField htmlFor="admin-users-search" label="Rechercher">
          <TextField
            id="admin-users-search"
            placeholder="Nom, courriel ou numéro de pratique"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="w-72"
          />
        </FilterField>
        <Button type="button" onClick={() => setEditing("new")}>
          <UserPlus aria-hidden />
          Nouvel utilisateur
        </Button>
      </div>

      {loading ? (
        <div aria-busy="true" aria-label="Chargement des utilisateurs" className="flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-12 rounded-lg" />
          ))}
        </div>
      ) : error ? (
        <Banner tone="error">{error}</Banner>
      ) : shown.length === 0 ? (
        <EmptyState icon={Users} title={users.length === 0 ? "Aucun utilisateur." : "Aucun utilisateur ne correspond."} />
      ) : (
        <>
          <div ref={listRef} className="scroll-mt-4 overflow-hidden rounded-xl border border-border bg-card">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-4">Utilisateur</TableHead>
                  <TableHead>Rôle</TableHead>
                  <TableHead>État</TableHead>
                  <TableHead>Dernière connexion</TableHead>
                  <TableHead className="text-right">Rencontres</TableHead>
                  <TableHead className="text-right">Réclamations</TableHead>
                  <TableHead className="w-0" aria-label="Actions" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {pages.items.map((user) => (
                  <TableRow key={user.id} className={user.is_active ? undefined : "text-muted-foreground"}>
                    <TableCell className="pl-4">
                      <p className="m-0 font-semibold">
                        {user.full_name}
                        {user.id === me?.id && <span className="ml-1.5 font-normal text-muted-foreground">(vous)</span>}
                      </p>
                      <p className="m-0 text-xs text-muted-foreground">
                        {user.email}
                        {user.practice_number && ` · nº ${user.practice_number}`}
                      </p>
                    </TableCell>
                    <TableCell>
                      <Badge tone={user.role === "admin" ? "primary" : "neutral"}>{ROLE_LABELS[user.role]}</Badge>
                    </TableCell>
                    <TableCell>
                      {!user.is_active ? (
                        <Badge tone="danger">Désactivé</Badge>
                      ) : user.must_change_password ? (
                        <Badge tone="warning">Mot de passe temporaire</Badge>
                      ) : (
                        <Badge tone="success">Actif</Badge>
                      )}
                    </TableCell>
                    <TableCell className="tabular-nums">{formatDateTime(user.last_login_at)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatCount(user.encounter_count)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatCount(user.claim_count)}</TableCell>
                    <TableCell className="pr-3">
                      <RowActions label={`Actions — ${user.full_name}`} actions={actionsFor(user)} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <Pagination {...pages} onChange={pages.setPage} listRef={listRef} className="mt-4" />
        </>
      )}
    </>
  );
}
