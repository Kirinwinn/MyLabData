import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { createQueryJobHandler, json } from "../tests/queryJobMock";
import { App } from "./App";

function renderApp(route = "/") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("application shell and dashboard", () => {
  it("loads the dashboard from the real API contract", async () => {
    const fetchMock = vi.fn(
      createQueryJobHandler(
        (url) => {
          if (url === "/api/v1/stats/query") {
            return {
              molecules: 1200,
              attributes: 18,
              entries: 44,
              annotations: 8432,
              imports: 7,
              jobs: 9,
            };
          }
          if (url === "/api/v1/imports/query") return { items: [] };
          return undefined;
        },
        (url) => {
          throw new Error(`Unexpected URL: ${url}`);
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderApp();

    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Database Summary" })).toBeInTheDocument();
    expect(await screen.findByText("1,200")).toBeInTheDocument();
    expect(screen.getByText("No import records yet")).toBeInTheDocument();
    expect(screen.queryByText("Jobs")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it.each([
    ["/imports", "Import"],
    ["/molecules", "Molecule records"],
    ["/search", "Filter"],
    ["/activity", "History"],
  ])("makes the planned route %s reachable", async (route, heading) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json([])));
    renderApp(route);
    await waitFor(() =>
      expect(
        heading === "Molecule records"
          ? screen.getByRole("region", { name: heading })
          : screen.getByRole("heading", { name: heading }),
      ).toBeInTheDocument(),
    );
  });

  it("makes the planned route /catalog reachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        createQueryJobHandler(
          (url) =>
            url === "/api/v1/attributes/query"
              ? {
                  items: [
                    {
                      attribute_id: 1,
                      attribute_key: "emission_wavelength",
                      attribute_name: "Emission Wavelength",
                      value_type: "number",
                      unit: "nm",
                      description: null,
                    },
                  ],
                }
              : undefined,
          (url) => {
            throw new Error(`Unexpected URL ${url}`);
          },
        ),
      ),
    );
    renderApp("/catalog");

    expect(await screen.findByPlaceholderText("Filter by name, key, or type")).toBeInTheDocument();
    const ones = screen.getAllByText("1");
    expect(ones.some((el) => el.className === "catalog-sidebar__count")).toBe(true);
    expect(ones.some((el) => el.className === "type-index")).toBe(true);
  });
});
