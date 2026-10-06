import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { makeUser, renderWithProviders, serveSession } from "../../test/render";
import { server } from "../../test/server";
import ChatbotPage from "./ChatbotPage";

beforeEach(() => serveSession(makeUser()));

type Turn = { role: string; content: string };

function serveChat(answer: string | ((query: string) => string) = "Réponse.") {
  const requests: { query: string; history: Turn[] }[] = [];
  server.use(
    http.post("/api/query", async ({ request }) => {
      const body = (await request.json()) as { query: string; history: Turn[] };
      requests.push(body);
      return HttpResponse.json({ answer: typeof answer === "function" ? answer(body.query) : answer });
    }),
  );
  return requests;
}

const box = () => screen.getByPlaceholderText("Posez une question de facturation...");
const send = () => screen.getByRole("button", { name: "Envoyer" });

describe("the RAMQ chat", () => {
  it("starts empty, with nothing to send or clear", () => {
    renderWithProviders(<ChatbotPage />);
    expect(screen.getByText("Posez une question pour commencer, par exemple :")).toBeInTheDocument();
    expect(send()).toBeDisabled();
    expect(screen.getByRole("button", { name: "Effacer la conversation" })).toBeDisabled();
  });

  it("sends a suggested question in one click", async () => {
    const requests = serveChat("Réponse.");
    const { user } = renderWithProviders(<ChatbotPage />);
    await user.click(screen.getByRole("button", { name: /visite de suivi et une visite périodique/ }));
    expect(await screen.findByText("Réponse.")).toBeInTheDocument();
    expect(requests).toHaveLength(1);
  });

  it("does not send a blank question", async () => {
    const requests = serveChat();
    const { user } = renderWithProviders(<ChatbotPage />);
    await user.type(box(), "   ");
    expect(send()).toBeDisabled();
    await user.type(box(), "{Enter}");
    expect(requests).toEqual([]);
  });

  it("sends the trimmed question, shows it and the answer, and empties the box", async () => {
    const requests = serveChat("Le code **00103** s'applique.");
    const { user } = renderWithProviders(<ChatbotPage />);
    await user.type(box(), "  Quel code pour une visite ?  ");
    await user.click(send());
    expect(await screen.findByText(/s'applique/)).toBeInTheDocument();
    expect(screen.getByText("Quel code pour une visite ?")).toBeInTheDocument();
    expect(requests).toEqual([{ query: "Quel code pour une visite ?", history: [] }]);
    expect(box()).toHaveValue("");
    expect(screen.queryByText("Posez une question pour commencer, par exemple :")).not.toBeInTheDocument();
  });

  it("renders the answer as markdown", async () => {
    serveChat("Voir **00103** et :\n\n- première\n- seconde");
    const { user } = renderWithProviders(<ChatbotPage />);
    await user.type(box(), "q");
    await user.click(send());
    expect(await screen.findByText("00103", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["première", "seconde"]);
  });

  it("sends with Enter, but Shift+Enter makes a new line", async () => {
    const requests = serveChat();
    const { user } = renderWithProviders(<ChatbotPage />);
    await user.type(box(), "ligne un{Shift>}{Enter}{/Shift}ligne deux");
    expect(requests).toEqual([]);
    expect(box()).toHaveValue("ligne un\nligne deux");
    await user.type(box(), "{Enter}");
    await screen.findByText("Réponse.");
    expect(requests[0].query).toBe("ligne un\nligne deux");
  });

  it("sends the earlier turns as history", async () => {
    const requests = serveChat((query) => `Réponse à ${query}`);
    const { user } = renderWithProviders(<ChatbotPage />);
    await user.type(box(), "un{Enter}");
    await screen.findByText("Réponse à un");
    await user.type(box(), "deux{Enter}");
    await screen.findByText("Réponse à deux");
    expect(requests[1].history).toEqual([
      { role: "user", content: "un" },
      { role: "assistant", content: "Réponse à un" },
    ]);
  });

  it("sends at most the last 20 messages as history", async () => {
    const requests = serveChat((query) => `R${query}`);
    const { user } = renderWithProviders(<ChatbotPage />);
    for (let i = 1; i <= 12; i++) {
      await user.type(box(), `q${i}{Enter}`);
      await screen.findByText(`Rq${i}`);
    }
    expect(requests[10].history).toHaveLength(20); // 11th question: 20 prior messages
    expect(requests[11].history).toHaveLength(20); // 12th: 22 prior, capped
    expect(requests[11].history[0]).toEqual({ role: "user", content: "q2" });
    expect(requests[11].history[19]).toEqual({ role: "assistant", content: "Rq11" });
  });

  it("shows a thinking state and blocks sending while waiting", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    server.use(
      http.post("/api/query", async () => {
        await gate;
        return HttpResponse.json({ answer: "Enfin." });
      }),
    );
    const { user } = renderWithProviders(<ChatbotPage />);
    await user.type(box(), "q");
    await user.click(send());
    expect(await screen.findByRole("status")).toHaveTextContent("Réflexion…");
    expect(screen.getByRole("button", { name: "Effacer la conversation" })).toBeDisabled();
    await user.type(box(), "autre{Enter}");
    release();
    await screen.findByText("Enfin.");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getAllByText("q")).toHaveLength(1);
  });

  it("shows the server's error, keeps the question in the conversation and recovers on the next one", async () => {
    let attempts = 0;
    server.use(
      http.post("/api/query", () =>
        ++attempts === 1 ? HttpResponse.json({ detail: "Service indisponible" }, { status: 503 }) : HttpResponse.json({ answer: "Ça marche." }),
      ),
    );
    const { user } = renderWithProviders(<ChatbotPage />);
    await user.type(box(), "première{Enter}");
    expect(await screen.findByText("Service indisponible")).toBeInTheDocument();
    expect(screen.getByText("première")).toBeInTheDocument();
    await user.type(box(), "deuxième{Enter}");
    expect(await screen.findByText("Ça marche.")).toBeInTheDocument();
    expect(screen.queryByText("Service indisponible")).not.toBeInTheDocument();
  });

  it("clears the conversation and the error", async () => {
    server.use(http.post("/api/query", () => HttpResponse.json({ detail: "Service indisponible" }, { status: 503 })));
    const { user } = renderWithProviders(<ChatbotPage />);
    await user.type(box(), "q{Enter}");
    await screen.findByText("Service indisponible");
    await user.click(screen.getByRole("button", { name: "Effacer la conversation" }));
    expect(screen.getByText("Posez une question pour commencer, par exemple :")).toBeInTheDocument();
    expect(screen.queryByText("Service indisponible")).not.toBeInTheDocument();
    expect(within(document.body).queryByText("q")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Effacer la conversation" })).toBeDisabled());
  });
});
