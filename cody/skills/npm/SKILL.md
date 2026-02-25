---
name: npm
description: Manage Node.js projects, dependencies, scripts, TypeScript setup, testing, and linting using npm/yarn/pnpm. Use when working with JavaScript or TypeScript projects.
metadata:
  author: cody
  version: "1.0"
compatibility: Requires node, npm
---

# Node.js / npm Project Management

Manage Node.js projects, dependencies, and scripts using npm (or yarn/pnpm).

## Prerequisites

- Node.js must be installed: `node --version`
- npm must be installed: `npm --version`

## Project Initialization

### Create a new project
```bash
npm init -y
```

### Common package.json scripts
```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "test": "jest",
    "lint": "eslint .",
    "format": "prettier --write ."
  }
}
```

## Dependency Management

### Install all dependencies
```bash
npm install
```

### Add a dependency
```bash
npm install express
npm install -D typescript @types/node    # Dev dependency
npm install -g nodemon                   # Global
```

### Remove a dependency
```bash
npm uninstall express
```

### Update dependencies
```bash
npm update
npm outdated                            # Check for outdated packages
```

### Check for vulnerabilities
```bash
npm audit
npm audit fix
```

## Running Scripts

### Run package scripts
```bash
npm run dev
npm run build
npm test           # Shorthand for npm run test
npm start          # Shorthand for npm run start
```

### Run a one-off command
```bash
npx create-next-app my-app
npx ts-node script.ts
```

## TypeScript Setup

### Initialize TypeScript
```bash
npm install -D typescript @types/node
npx tsc --init
```

### Common tsconfig.json
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "lib": ["ES2020"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

## Testing

### Jest setup
```bash
npm install -D jest @types/jest ts-jest
```

### Run tests
```bash
npm test
npm test -- --watch
npm test -- --coverage
npm test -- --testPathPattern="auth"
```

## Linting & Formatting

### ESLint
```bash
npm install -D eslint
npx eslint --init
npx eslint . --fix
```

### Prettier
```bash
npm install -D prettier
npx prettier --write .
```

## Framework-Specific

### Next.js
```bash
npx create-next-app@latest my-app
npm run dev     # Start development server
npm run build   # Production build
```

### Express
```bash
npm install express
npm install -D @types/express nodemon
```

## Monorepo (npm workspaces)

```json
{
  "workspaces": ["packages/*"]
}
```

```bash
npm install                           # Install all workspace deps
npm run build -w packages/core        # Run script in specific workspace
npm install lodash -w packages/core   # Add dep to specific workspace
```

## Notes

- Always commit `package-lock.json` to version control
- Use `--save-exact` or `~` for critical dependencies
- Check `node_modules` is in `.gitignore`
- Use `npm ci` in CI/CD (faster, uses lockfile exactly)
- Use `engines` field to specify required Node.js version
