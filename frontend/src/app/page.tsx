'use client';

import { HubView } from '@/components/sentinel/views/HubView';
import { MHub, MobileSwap } from '@/components/sentinel/MobileViews';

export default function HomePage() {
  return <MobileSwap desktop={<HubView />} mobile={<MHub />} />;
}
