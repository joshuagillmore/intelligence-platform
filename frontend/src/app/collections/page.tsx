'use client';

import { AcquireView } from '@/components/sentinel/views/AcquireView';
import { MAcquire, MobileSwap } from '@/components/sentinel/MobileViews';

export default function CollectionsPage() {
  return <MobileSwap desktop={<AcquireView />} mobile={<MAcquire />} />;
}
