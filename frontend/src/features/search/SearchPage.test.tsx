import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router";

import { App } from "../../app/App";
import { createQueryJobHandler, json } from "../../tests/queryJobMock";

const attributes = [
  {
    attribute_id: 1,
    attribute_key: "emission_wavelength",
    attribute_name: "Emission Wavelength",
    value_type: "number",
    unit: "nm",
    description: null,
  },
  {
    attribute_id: 2,
    attribute_key: "is_fluorescent",
    attribute_name: "Is Fluorescent",
    value_type: "boolean",
    unit: null,
    description: null,
  },
];

const entries = {
  1: [
    {
      entry_id: 10,
      attribute_id: 1,
      entry_key: "emission_wavelength.proby_dmso",
      annotation_kind: "property",
      method_name: "Fluorimeter",
      method_version: null,
      conditions: {},
      is_mutable: true,
      description: null,
    },
  ],
  2: [
    {
      entry_id: 11,
      attribute_id: 2,
      entry_key: "is_fluorescent.visual_check",
      annotation_kind: "property",
      method_name: "Visual",
      method_version: null,
      conditions: {},
      is_mutable: true,
      description: null,
    },
  ],
};

const searchResult = {
  molecules: [
    {
      molecule_id: 7,
      lab_id: "MLD-0007",
      canonical_smiles: "CCO",
      created_at: "2026-08-27T00:00:00Z",
    },
  ],
  elapsed_ms: 1.2345,
  limit: 25,
  offset: 0,
  total: 1,
};

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
}

function renderSearch(route = "/search") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <App />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("multi-condition Search", () => {
  it("builds a typed OR request, saves it to URL and renders Molecule summaries", async () => {
    let submittedBody: unknown;
    const fetchMock = vi.fn(
      createQueryJobHandler(
        (url, init) => {
          if (url === "/api/v1/attributes/query") return { items: attributes };
          if (url === "/api/v1/attributes/1/entries/query") return { items: entries[1] };
          if (url === "/api/v1/attributes/2/entries/query") return { items: entries[2] };
          if (url === "/api/v1/search") {
            submittedBody = JSON.parse(String(init?.body)) as unknown;
            return searchResult;
          }
          return undefined;
        },
        (url) => {
          throw new Error(`Unexpected URL ${url}`);
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderSearch();

    await screen.findByRole("option", { name: "Emission Wavelength" });
    await user.selectOptions(screen.getByLabelText("Condition 1 Attribute"), "1");
    await screen.findByRole("option", { name: "emission_wavelength.proby_dmso" });
    await user.selectOptions(screen.getByLabelText("Condition 1 Entry"), "10");
    await user.selectOptions(screen.getByLabelText("Condition 1 Operator"), "between");
    await user.type(screen.getByLabelText("Condition 1 Value"), "500");
    await user.type(screen.getByLabelText("Condition 1 Second Value"), "600");

    await user.click(screen.getByRole("button", { name: "＋ Add condition" }));
    await user.selectOptions(screen.getByLabelText("Condition 2 Attribute"), "2");
    await screen.findByRole("option", { name: "is_fluorescent.visual_check" });
    await user.selectOptions(screen.getByLabelText("Condition 2 Entry"), "11");
    await user.selectOptions(screen.getByLabelText("Condition 2 Value"), "false");
    await user.click(screen.getByRole("radio", { name: /OR/ }));
    await user.click(screen.getByRole("button", { name: "Run Search" }));

    expect(await screen.findByRole("link", { name: "MLD-0007" })).toHaveAttribute(
      "href",
      "/molecules/7",
    );
    expect(submittedBody).toEqual({
      conditions: [
        {
          attribute_id: 1,
          entry_id: 10,
          operator: "between",
          value: 500,
          second_value: 600,
        },
        { attribute_id: 2, entry_id: 11, operator: "eq", value: false },
      ],
      logic: "or",
      limit: 25,
      offset: 0,
    });
    expect(screen.getByTestId("location").textContent).toContain("query=");
  });

  it("restores submitted conditions from URL and prevents an invalid number range", async () => {
    const savedRequest = {
      conditions: [
        {
          attribute_id: 1,
          entry_id: 10,
          operator: "between",
          value: 500,
          second_value: 600,
        },
      ],
      logic: "and",
      limit: 25,
      offset: 0,
    };
    const fetchMock = vi.fn(
      createQueryJobHandler(
        (url) => {
          if (url === "/api/v1/attributes/query") return { items: attributes };
          if (url === "/api/v1/attributes/1/entries/query") return { items: entries[1] };
          if (url === "/api/v1/search") {
            return { molecules: [], elapsed_ms: 0.2, limit: 25, offset: 0, total: 0 };
          }
          return undefined;
        },
        (url) => {
          throw new Error(`Unexpected URL ${url}`);
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const route = `/search?${new URLSearchParams({ query: JSON.stringify(savedRequest) })}`;
    const user = userEvent.setup();
    renderSearch(route);

    await screen.findByRole("option", { name: "Emission Wavelength" });
    await screen.findByRole("option", { name: "emission_wavelength.proby_dmso" });
    expect(screen.getByLabelText("Condition 1 Attribute")).toHaveValue("1");
    expect(screen.getByLabelText("Condition 1 Entry")).toHaveValue("10");
    expect(screen.getByLabelText("Condition 1 Operator")).toHaveValue("between");
    expect(screen.getByLabelText("Condition 1 Value")).toHaveValue(500);
    expect(screen.getByLabelText("Condition 1 Second Value")).toHaveValue(600);

    await user.clear(screen.getByLabelText("Condition 1 Value"));
    await user.type(screen.getByLabelText("Condition 1 Value"), "700");
    await user.click(screen.getByRole("button", { name: "Run Search" }));
    expect(
      await screen.findByText("Condition 1: Minimum cannot be greater than maximum."),
    ).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
  });

  it("offers only operators valid for the selected value type", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        createQueryJobHandler(
          (url) => {
            if (url === "/api/v1/attributes/query") return { items: attributes };
            if (url === "/api/v1/attributes/1/entries/query") return { items: entries[1] };
            if (url === "/api/v1/attributes/2/entries/query") return { items: entries[2] };
            return undefined;
          },
          (url) => {
            throw new Error(`Unexpected URL ${url}`);
          },
        ),
      ),
    );
    const user = userEvent.setup();
    renderSearch();

    await screen.findByRole("option", { name: "Emission Wavelength" });
    await user.selectOptions(screen.getByLabelText("Condition 1 Attribute"), "1");
    const numericOperators = screen.getByLabelText("Condition 1 Operator");
    expect(numericOperators).toHaveTextContent("between");
    expect(numericOperators).not.toHaveTextContent("contains");

    await user.selectOptions(screen.getByLabelText("Condition 1 Attribute"), "2");
    const booleanOperators = screen.getByLabelText("Condition 1 Operator");
    expect(booleanOperators).toHaveTextContent("eq");
    expect(booleanOperators).toHaveTextContent("ne");
    expect(booleanOperators).not.toHaveTextContent("between");
  });
});

describe("search export", () => {
  const exportResult = {
    file_name: "search_export_test.xlsx",
    logic: "and",
    total: 1,
    sheets: [
      { title: "Summary", row_count: 2 },
      { title: "Molecules", row_count: 1 },
    ],
  };

  function catalogResolver(
    searchPayload: unknown,
    exportSink?: { body?: unknown },
  ) {
    return (url: string, init?: RequestInit) => {
      if (url === "/api/v1/attributes/query") return { items: attributes };
      if (url === "/api/v1/attributes/1/entries/query") return { items: entries[1] };
      if (url === "/api/v1/search") return searchPayload;
      if (url === "/api/v1/search/export" && exportSink) {
        exportSink.body = JSON.parse(String(init?.body)) as unknown;
        return exportResult;
      }
      return undefined;
    };
  }

  async function runEmissionSearch(user: ReturnType<typeof userEvent.setup>) {
    await screen.findByRole("option", { name: "Emission Wavelength" });
    await user.selectOptions(screen.getByLabelText("Condition 1 Attribute"), "1");
    await screen.findByRole("option", { name: "emission_wavelength.proby_dmso" });
    await user.selectOptions(screen.getByLabelText("Condition 1 Entry"), "10");
    await user.selectOptions(screen.getByLabelText("Condition 1 Operator"), "gt");
    await user.type(screen.getByLabelText("Condition 1 Value"), "500");
    await user.click(screen.getByRole("button", { name: "Run Search" }));
  }

  it("exports the current search and triggers the workbook download", async () => {
    const downloadedUrls: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloadedUrls.push(this.href);
    });
    const exportSink: { body?: unknown } = {};
    vi.stubGlobal(
      "fetch",
      vi.fn(
        createQueryJobHandler(
          catalogResolver(searchResult, exportSink),
          (url) => {
            throw new Error(`Unexpected URL ${url}`);
          },
        ),
      ),
    );
    const user = userEvent.setup();
    renderSearch();

    await runEmissionSearch(user);
    const exportButton = await screen.findByRole("button", { name: "Export XLSX" });
    expect(exportButton).toBeEnabled();

    await user.click(exportButton);

    await waitFor(() => expect(downloadedUrls).toHaveLength(1));
    expect(downloadedUrls[0]).toMatch(/\/api\/v1\/jobs\/[^/]+\/export$/);
    expect(exportSink.body).toEqual({
      conditions: [{ attribute_id: 1, entry_id: 10, operator: "gt", value: 500 }],
      logic: "and",
      limit: 25,
      offset: 0,
    });
    expect(await screen.findByRole("button", { name: "Export XLSX" })).toBeEnabled();
  });

  it("keeps the export button busy and prevents re-clicks while the job runs", async () => {
    let releaseJob!: (response: Response) => void;
    const jobGate = new Promise<Response>((resolve) => {
      releaseJob = resolve;
    });
    const downloadedUrls: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloadedUrls.push(this.href);
    });
    const completedJob = (jobId: string, result: unknown) => ({
      job_id: jobId,
      job_type: "test_query",
      job_kind: "query",
      status: "completed",
      result,
      error_message: null,
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (init?.method === "POST" && url === "/api/v1/attributes/query") {
          return json({ job_id: "attrs-job", status: "queued" }, 202);
        }
        if (init?.method === "POST" && url === "/api/v1/attributes/1/entries/query") {
          return json({ job_id: "entries-job", status: "queued" }, 202);
        }
        if (init?.method === "POST" && url === "/api/v1/search") {
          return json({ job_id: "search-job", status: "queued" }, 202);
        }
        if (url === "/api/v1/jobs/attrs-job") {
          return json(completedJob("attrs-job", { items: attributes }));
        }
        if (url === "/api/v1/jobs/entries-job") {
          return json(completedJob("entries-job", { items: entries[1] }));
        }
        if (url === "/api/v1/jobs/search-job") {
          return json(completedJob("search-job", searchResult));
        }
        if (init?.method === "POST" && url === "/api/v1/search/export") {
          return json({ job_id: "export-job", status: "queued" }, 202);
        }
        if (url === "/api/v1/jobs/export-job") {
          return await jobGate;
        }
        throw new Error(`Unexpected request ${url}`);
      }),
    );
    const user = userEvent.setup();
    renderSearch();

    await runEmissionSearch(user);
    await user.click(await screen.findByRole("button", { name: "Export XLSX" }));

    const busyButton = await screen.findByRole("button", { name: "Exporting…" });
    expect(busyButton).toBeDisabled();

    releaseJob(json(completedJob("export-job", exportResult)));
    await waitFor(() => expect(downloadedUrls).toHaveLength(1));
    expect(await screen.findByRole("button", { name: "Export XLSX" })).toBeEnabled();
  });

  it("disables exporting while there are no matching molecules", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        createQueryJobHandler(
          catalogResolver({ molecules: [], elapsed_ms: 0.2, limit: 25, offset: 0, total: 0 }),
          (url) => {
            throw new Error(`Unexpected URL ${url}`);
          },
        ),
      ),
    );
    const user = userEvent.setup();
    renderSearch();

    await runEmissionSearch(user);
    expect(await screen.findByText("No matching molecules")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export XLSX" })).toBeDisabled();
  });

  it("shows an error message when the export job fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        createQueryJobHandler(
          catalogResolver(searchResult),
          (url) => {
            if (url === "/api/v1/search/export") {
              return json({ job_id: "export-job", status: "queued" }, 202);
            }
            if (url === "/api/v1/jobs/export-job") {
              return json({
                job_id: "export-job",
                job_type: "search_export",
                job_kind: "query",
                status: "failed",
                result: null,
                error_message: "Export workbook generation failed",
              });
            }
            throw new Error(`Unexpected URL ${url}`);
          },
        ),
      ),
    );
    const user = userEvent.setup();
    renderSearch();

    await runEmissionSearch(user);
    await user.click(await screen.findByRole("button", { name: "Export XLSX" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Export workbook generation failed",
    );
    expect(screen.getByRole("button", { name: "Export XLSX" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Export XLSX" })).not.toHaveTextContent(
      "Exporting…",
    );
  });
});
