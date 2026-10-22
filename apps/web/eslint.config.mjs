import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // Tokens only (AGENTS.md §8): no raw hex colours in components. The root layout's theme-color meta
    // is the one exception (browsers can't read CSS variables there).
    files: ["src/components/**/*.{ts,tsx}", "src/app/**/*.tsx"],
    ignores: ["src/app/layout.tsx"],
    rules: {
      "no-restricted-syntax": [
        "error",
        { selector: "Literal[value=/#[0-9a-fA-F]{3,8}(?![0-9a-zA-Z])/]", message: "Use a design token, not a raw hex colour." },
        { selector: "TemplateElement[value.raw=/#[0-9a-fA-F]{3,8}(?![0-9a-zA-Z])/]", message: "Use a design token, not a raw hex colour." },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "playwright-report/**",
    "test-results/**",
  ]),
]);

export default eslintConfig;
