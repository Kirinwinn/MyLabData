import { describe, expect, it } from "vitest";

import type { SearchRequest } from "../../api";
import { searchRequestFromUrl, searchRequestToUrl } from "./searchState";

describe("search URL state", () => {
  it("round-trips submitted AND/OR conditions and pagination", () => {
    const request: SearchRequest = {
      conditions: [
        {
          attribute_id: 1,
          entry_id: 10,
          operator: "between",
          value: 500,
          second_value: 600,
        },
        { attribute_id: 2, entry_id: 11, operator: "eq", value: true },
      ],
      logic: "or",
      limit: 25,
      offset: 50,
    };

    const parameters = searchRequestToUrl(request);

    expect(searchRequestFromUrl(parameters)).toEqual(request);
    expect(parameters.toString()).toContain("query=");
  });

  it("rejects malformed URL state without producing a backend request", () => {
    const parameters = new URLSearchParams({
      query: JSON.stringify({
        conditions: [{ attribute_id: -1, entry_id: 2, operator: "contains", value: 1 }],
        logic: "and",
        limit: 25,
        offset: 0,
      }),
    });

    expect(searchRequestFromUrl(parameters)).toBeNull();
    expect(searchRequestFromUrl(new URLSearchParams({ query: "not-json" }))).toBeNull();
  });
});
