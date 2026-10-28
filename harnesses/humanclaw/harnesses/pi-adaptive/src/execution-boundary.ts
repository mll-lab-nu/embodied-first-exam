/** A model may inspect the next observation only in its next request.
 * Explicit programs have their own reviewed broker-mediated child execution.
 */
export class ExecutionBoundary {
  private turns = new WeakMap<object, string>();

  admit(turn: object, name: string, args: unknown): string | undefined {
    const previous = this.turns.get(turn);
    const fingerprint = JSON.stringify({name, args});
    const action = (args as {action?: string} | undefined)?.action;
    const execution = name === "adaptive__execute" || (name === "adaptive__adapter" && (action === "probe" || action === "reconcile"));
    if (previous !== undefined) {
      if (name === "adaptive__receipt") return;
      if (execution && previous === fingerprint) return;
      return "An execution was already attempted in this model turn. Inspect its result in a new model request before updating evidence, claiming completion or choosing further work. Do not guess the next observation.";
    }
    if (execution) this.turns.set(turn, fingerprint);
  }
}
