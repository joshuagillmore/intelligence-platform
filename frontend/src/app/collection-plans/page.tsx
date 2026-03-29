'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/**
 * Collection Plans has been merged into the unified Collections page.
 * This page redirects to /collections for backwards compatibility.
 */
export default function CollectionPlansPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/collections');
  }, [router]);
  return null;
}
