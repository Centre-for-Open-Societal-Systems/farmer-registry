// server/cache.ts
import { LRUCache } from 'lru-cache';

// In-memory cache for chart data
const cache = new LRUCache<string, any>({
    max: 500, // Maximum 500 entries
    ttl: 1000 * 60 * 5, // 5 minutes TTL
    updateAgeOnGet: true,
    updateAgeOnHas: true,
});

export function getCachedData<T>(key: string): T | undefined {
    return cache.get(key) as T | undefined;
}

export function setCachedData<T>(key: string, data: T): void {
    cache.set(key, data);
}

export function clearCache(): void {
    cache.clear();
}

export function deleteCachedData(key: string): void {
    cache.delete(key);
}

// Helper to generate cache keys
export function generateCacheKey(prefix: string, params: Record<string, any>): string {
    const sortedParams = Object.keys(params)
        .sort()
        .reduce((acc, key) => {
            acc[key] = params[key];
            return acc;
        }, {} as Record<string, any>);

    return `${prefix}:${JSON.stringify(sortedParams)}`;
}
