/** Which nodes get an on-canvas text label.
 *
 *  Every node used to carry one. At the 500-node display budget that put 500
 *  labels at 9px on top of each other: text layered over text through the whole
 *  dense core, most of it truncated mid-word, none of it readable. A label
 *  nobody can read is worse than no label — it is noise drawn over the graph.
 *
 *  So labels are a budget too. The most-connected nodes earn one, because they
 *  are the ones an analyst is orienting by; everything else is recoverable on
 *  hover, where the full name already appears as a tooltip.
 */

/** How many labels a canvas can hold before they start colliding.
 *
 *  Empirical, at the 1440x900 the app is actually used at: ~40 labels sit
 *  comfortably around a 500-node force layout. It is a display constant, not a
 *  data one — it does not change with graph size, which is the point.
 */
export const LABEL_BUDGET = 40;

export interface LabelCandidate {
  id: string;
  /** Aggregate nodes stand for many entities and are meaningless unnamed. */
  isCommunity?: boolean;
}

/** The ids that should be labelled, given each node's degree.
 *
 *  Community super-nodes are always labelled and do not consume the budget:
 *  an unnamed aggregate is not something the analyst can hover to identify,
 *  since the name is the only thing that says what was collapsed.
 */
export function labelledNodeIds(
  nodes: LabelCandidate[],
  degree: Record<string, number>,
  budget: number = LABEL_BUDGET,
): Set<string> {
  // Nothing is crowded if the whole graph fits, so ration nothing. Without
  // this, the cyber panel's 4-node / 0-edge graph rendered four anonymous
  // dots: every node had degree 0, so the ranking below excluded all of them.
  // The budget is a response to crowding, not a property of the data.
  if (nodes.length <= budget) {
    return new Set(nodes.map(n => n.id));
  }

  const labelled = new Set<string>();
  const ranked: LabelCandidate[] = [];

  for (const n of nodes) {
    if (n.isCommunity) labelled.add(n.id);
    else ranked.push(n);
  }

  // Ties broken by id so the same graph always labels the same nodes; a layout
  // that relabels different hubs on every render reads as flicker.
  ranked.sort((a, b) => {
    const d = (degree[b.id] || 0) - (degree[a.id] || 0);
    return d !== 0 ? d : a.id.localeCompare(b.id);
  });

  // Counted separately from `labelled` so community nodes genuinely do not
  // consume the budget — sharing the counter silently let a handful of
  // aggregates displace the hubs the budget exists to name.
  let spent = 0;
  for (const n of ranked) {
    if (spent >= budget) break;
    // A node with no edges at all is not a landmark: it has nothing to orient
    // by and is the bulk of what crowded the canvas. Ranked descending, so the
    // first zero means the rest are zero too.
    if ((degree[n.id] || 0) === 0) break;
    labelled.add(n.id);
    spent++;
  }

  return labelled;
}
