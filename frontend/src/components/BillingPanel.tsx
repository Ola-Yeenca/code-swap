import { useMutation, useQuery } from "@tanstack/react-query";

import { billingCheckout, billingEntitlements, billingStatus } from "../api/client";

interface Props {
  workspaceId?: string;
}

export function BillingPanel({ workspaceId }: Props) {
  const statusQuery = useQuery({
    queryKey: ["billing-status", workspaceId],
    queryFn: () => billingStatus(workspaceId as string),
    enabled: Boolean(workspaceId),
    retry: false,
  });

  const entitlementsQuery = useQuery({
    queryKey: ["billing-entitlements", workspaceId],
    queryFn: () => billingEntitlements(workspaceId as string),
    enabled: Boolean(workspaceId),
    retry: false,
  });

  const checkoutMutation = useMutation({
    mutationFn: () => billingCheckout(workspaceId as string),
    onSuccess: (result) => {
      window.open(result.url, "_blank", "noopener,noreferrer");
    },
  });

  return (
    <section className="panel p-4">
      <h2 className="font-display text-lg font-semibold">Billing</h2>
      <p className="mt-1 text-sm text-slate-600">Stripe-ready owner billing controls.</p>

      {!workspaceId ? <p className="mt-2 text-sm">Select a workspace to view billing.</p> : null}

      {workspaceId ? (
        <>
          <button
            className="mt-3 w-full rounded bg-brass px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
            type="button"
            disabled={checkoutMutation.isPending}
            onClick={() => checkoutMutation.mutate()}
          >
            {checkoutMutation.isPending ? "Starting..." : "Start Checkout"}
          </button>

          {statusQuery.isError ? (
            <p className="mt-2 text-xs text-slate-700">Billing disabled or owner role required.</p>
          ) : null}

          {statusQuery.data ? (
            <div className="mt-3 rounded border border-slate-200 bg-white p-2 text-xs">
              <div>Status: {statusQuery.data.subscriptionStatus}</div>
              <div>Customer: {statusQuery.data.customerId || "none"}</div>
            </div>
          ) : null}

          {entitlementsQuery.data?.length ? (
            <div className="mt-2 space-y-1 text-xs">
              {entitlementsQuery.data.map((item) => (
                <div key={item.featureKey} className="rounded border border-slate-200 bg-white p-2">
                  {item.featureKey}: {item.isEnabled ? "enabled" : "disabled"}
                </div>
              ))}
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
