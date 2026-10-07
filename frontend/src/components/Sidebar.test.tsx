import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Inbox } from "lucide-react";
import { afterEach, describe, expect, it } from "vitest";
import { NavItem, NavSection, Sidebar } from "./Sidebar";

function renderSidebar() {
  return {
    user: userEvent.setup(),
    ...render(
      <MemoryRouter>
        <Sidebar>
          <NavSection title="Référence RAMQ">
            <NavItem to="/app/inbox" icon={Inbox} count={3}>
              Rencontres
            </NavItem>
          </NavSection>
        </Sidebar>
      </MemoryRouter>,
    ),
  };
}

describe("Sidebar", () => {
  afterEach(() => window.localStorage.clear());

  it("folds to an icon rail that keeps every link's name, and remembers it", async () => {
    const { user, unmount } = renderSidebar();
    expect(screen.getByText("Référence RAMQ")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Replier le menu" }));

    expect(screen.getByRole("link", { name: "Rencontres" })).toHaveAttribute("title", "Rencontres");
    expect(screen.queryByText("3")).not.toBeInTheDocument();
    expect(screen.getByRole("separator", { name: "Référence RAMQ" })).toBeInTheDocument();

    unmount();
    renderSidebar();
    expect(screen.getByRole("button", { name: "Déplier le menu" })).toHaveAttribute("aria-expanded", "false");
  });
});
