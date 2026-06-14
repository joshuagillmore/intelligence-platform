'use client';

import { GraphView } from '@/components/sentinel/views/GraphView';
import { MAsk, MobileSwap } from '@/components/sentinel/MobileViews';

export default function NetworkPage() {
  return <MobileSwap desktop={<GraphView />} mobile={<MAsk />} />;
}
