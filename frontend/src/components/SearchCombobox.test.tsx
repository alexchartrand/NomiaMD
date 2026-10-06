import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SearchCombobox } from "./SearchCombobox";

const FRUITS = ["pomme", "poire", "prune"];

function setup({ minChars = 1, onPick = vi.fn() }: { minChars?: number; onPick?: (item: string) => void } = {}) {
  const queries: string[] = [];
  const search = async (q: string) => {
    queries.push(q);
    return FRUITS.filter((f) => f.startsWith(q));
  };
  render(
    <SearchCombobox<string>
      search={search}
      itemKey={(f) => f}
      renderItem={(f) => f}
      onPick={onPick}
      minChars={minChars}
      emptyText={(q) => (q ? "Rien" : "Tapez")}
      emptyQueryHeading="Fréquents"
      ariaLabel="Fruit"
    />,
  );
  return { queries, onPick, user: userEvent.setup(), input: screen.getByRole("combobox", { name: "Fruit" }) };
}

describe("SearchCombobox", () => {
  it("moves through the matches with the arrow keys and picks with Enter", async () => {
    const { user, input, onPick } = setup();
    await user.type(input, "p");
    await screen.findByRole("option", { name: "pomme" });
    expect(screen.getByRole("option", { name: "pomme" })).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}{ArrowUp}");
    expect(screen.getByRole("option", { name: "poire" })).toHaveAttribute("aria-selected", "true");
    expect(input).toHaveAttribute("aria-activedescendant", screen.getByRole("option", { name: "poire" }).id);

    await user.keyboard("{Enter}");
    expect(onPick).toHaveBeenCalledWith("poire");
    // Without a selectedLabel, the field empties for the next search.
    expect(input).toHaveValue("");
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
  });

  it("closes the list on Escape", async () => {
    const { user, input } = setup();
    await user.type(input, "po");
    await screen.findByRole("option", { name: "pomme" });
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
  });

  it("with minChars 0, searches on focus with an empty query under its heading", async () => {
    const { user, input, queries } = setup({ minChars: 0 });
    await user.click(input);
    expect(await screen.findByText("Fréquents")).toBeInTheDocument();
    expect(queries).toEqual([""]);
    expect(screen.getAllByRole("option")).toHaveLength(3);
  });

  it("says when nothing matches", async () => {
    const { user, input } = setup();
    await user.type(input, "zz");
    expect(await screen.findByText("Rien")).toBeInTheDocument();
  });

  it("picks with a click", async () => {
    const { user, input, onPick } = setup();
    await user.type(input, "pr");
    await user.click(await screen.findByRole("option", { name: "prune" }));
    await waitFor(() => expect(onPick).toHaveBeenCalledWith("prune"));
  });
});
