import Welcome from "@/components/Welcome";

export const dynamic = "force-dynamic";

// The front door. A first-time visitor gets one question and nothing else; a visitor who has answered is sent by
// web/proxy.ts to their own home page (app/home/[type]/[answer]), and one who skipped to the markets page.
export default function FrontDoor() {
  return <Welcome />;
}
