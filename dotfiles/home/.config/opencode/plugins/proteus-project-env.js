import { homedir } from "node:os";

// shell.env runs for each command, after the provider's own launch environment.
// No dependencies or Node selection at plugin load: OpenCode uses its own runtime.
export const ProteusProjectEnvironment = async () => ({
  "shell.env": async (_input, output) => {
    const home = homedir();
    const inherited = output.env.PATH ?? process.env.PATH ?? "/usr/local/bin:/usr/bin:/bin";
    output.env.PATH = `${home}/.local/bin:${home}/.local/share/mise/shims:${inherited}`;
  },
});
