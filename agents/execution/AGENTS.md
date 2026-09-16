# Project Name

Next.js 15 App Router, React 19, TypeScript 5.4, Tailwind CSS, Drizzle ORM, Bun.

## Commands

Build: `bun run build`
Test: `bun test`
Lint: `bun run lint --fix`
Single test: `bun test path/to/file.test.ts`

## Code Style

Functional components only. Never class components.
Use `const` exclusively. Never `var`, never `let` unless reassignment is needed.
Named exports only. Never default exports.

// Component pattern:
export const UserCard = ({ name, email }: UserCardProps) => {
return <div className="p-4">{name}</div>;
};

## Error Handling

Let errors propagate. Do not wrap individual calls in try/catch.
The global error handler in middleware.ts catches everything.

## Architecture

/app -> Routes and page components
/components -> Shared UI components
/lib -> Business logic and utilities
/db -> Database schema and migrations

Never import from /app into /lib. Data flows one direction.

## Boundaries

Never modify files in /generated/.
Never commit .env or any file containing secrets.
The /legacy/ module uses sync patterns. Do not convert to async.

## Git

Squash merge only.
Conventional commits: feat:, fix:, chore:, docs:.
Branch format: type/short-description (e.g., feat/user-auth).
