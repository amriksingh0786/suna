import { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Agent Conversation | Incentiv Atlas AI',
  description: 'Interactive agent conversation powered by Incentiv Atlas AI',
  openGraph: {
    title: 'Agent Conversation | Incentiv Atlas AI',
    description: 'Interactive agent conversation powered by Incentiv Atlas AI',
    type: 'website',
  },
};

export default function AgentsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
