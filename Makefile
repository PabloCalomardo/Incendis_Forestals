.PHONY: install dev build lint typecheck test migrate reset-db

install:
	npm run install:all

dev:
	npm run dev

build:
	npm run build

lint:
	npm run lint

typecheck:
	npm run typecheck

test:
	npm run test

migrate:
	npm run migrate

reset-db:
	npm run reset-db
