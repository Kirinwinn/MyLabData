import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";

import { apiClient, ApiError, queryKeys } from "../../api";

function errorMessage(error: Error) {
  return error instanceof ApiError ? error.message : "Unable to load attributes.";
}

export function MoleculeAttributeDirectory({ moleculeId }: { moleculeId: number }) {
  const [searchParameters, setSearchParameters] = useSearchParams();
  const selectedAttributeId = Number(searchParameters.get("attribute"));
  const attributes = useQuery({
    queryKey: queryKeys.molecules.attributes(moleculeId),
    queryFn: ({ signal }) => apiClient.moleculeAttributes(moleculeId, { signal }),
    enabled: Number.isSafeInteger(moleculeId) && moleculeId > 0,
  });

  return (
    <section className="molecule-attribute-directory" aria-labelledby="attribute-directory-title">
      <h2 id="attribute-directory-title">Attributes</h2>
      {attributes.isPending ? <p>Loading attributes...</p> : null}
      {attributes.error ? <p>{errorMessage(attributes.error)}</p> : null}
      {!attributes.isPending && !attributes.error && !attributes.data?.length ? (
        <p>No attributes available.</p>
      ) : null}
      {attributes.data?.length ? (
        <nav aria-label="Molecule attributes">
          {attributes.data.map((attribute) => {
            const active = attribute.attribute_id === selectedAttributeId;
            return (
              <button
                aria-current={active ? "page" : undefined}
                className={
                  active
                    ? "molecule-attribute-directory__item is-active"
                    : "molecule-attribute-directory__item"
                }
                key={attribute.attribute_id}
                onClick={() => {
                  const next = new URLSearchParams(searchParameters);
                  next.set("attribute", String(attribute.attribute_id));
                  setSearchParameters(next);
                }}
                type="button"
              >
                {attribute.attribute_name}
              </button>
            );
          })}
        </nav>
      ) : null}
    </section>
  );
}
