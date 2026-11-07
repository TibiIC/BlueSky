import { MongoClient, type Db, type MongoClientOptions } from 'mongodb';
import { MONGODB_DB, MONGODB_URI } from '$app/env/private';

/** One client per server process; the driver pools connections itself. */
let client: Promise<MongoClient> | null = null;

export const dbConfigured = () => !!MONGODB_URI;

/** The app database, or null when MONGODB_URI is not set (the app then works without saving). */
export async function getDb(): Promise<Db | null> {
	if (!MONGODB_URI) return null;
	// Cast: without @types/node the driver's TLS option types resolve as required fields.
	client ??= new MongoClient(MONGODB_URI, { appName: 'bluesky', serverSelectionTimeoutMS: 8000 } as MongoClientOptions)
		.connect()
		.then(async (c) => {
			const db = c.db(MONGODB_DB);
			await Promise.all([
				db.collection('reports').createIndex({ reportId: 1, version: -1 }, { unique: true }),
				db.collection('reviews').createIndex({ reportId: 1, at: 1 })
			]);
			return c;
		})
		.catch((e) => {
			client = null; // retry on the next request
			throw e;
		});
	return (await client).db(MONGODB_DB);
}
