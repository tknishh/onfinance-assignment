"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const dark = theme !== "light";
  return (
    <Button
      variant="ghost"
      size="icon"
      className="size-9 rounded-full"
      onClick={() => setTheme(dark ? "light" : "dark")}
      aria-label="Toggle theme"
    >
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}
