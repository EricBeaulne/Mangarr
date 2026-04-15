import { NavLink } from 'react-router-dom';
import { BookOpen, PlusCircle, FolderOpen, Search, Settings, ListX } from 'lucide-react';
import clsx from 'clsx';

interface NavItem {
  to: string;
  icon: React.ReactNode;
  label: string;
  end?: boolean;
}

const navItems: NavItem[] = [
  { to: '/', icon: <BookOpen className="w-5 h-5" />, label: 'Library', end: true },
  { to: '/wanted', icon: <ListX className="w-5 h-5" />, label: 'Wanted' },
  { to: '/add', icon: <PlusCircle className="w-5 h-5" />, label: 'Add Series' },
  { to: '/settings/folders', icon: <FolderOpen className="w-5 h-5" />, label: 'Root Folders' },
  { to: '/scanner', icon: <Search className="w-5 h-5" />, label: 'Scanner' },
  { to: '/settings', icon: <Settings className="w-5 h-5" />, label: 'Settings', end: true },
];

export function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 bottom-0 w-60 bg-mangarr-card border-r border-mangarr-border flex flex-col z-40">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-mangarr-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-mangarr-accent rounded-lg flex items-center justify-center shrink-0">
            <BookOpen className="w-4 h-4 text-white" />
          </div>
          <div>
            <span className="text-mangarr-text font-bold text-lg leading-none block">
              Mangarr
            </span>
            <span className="text-mangarr-muted text-xs">Manga Library Manager</span>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors duration-150',
                'border-l-2',
                isActive
                  ? 'bg-mangarr-accent/10 text-mangarr-accent border-mangarr-accent'
                  : 'text-mangarr-muted hover:text-mangarr-text hover:bg-mangarr-input border-transparent',
              )
            }
          >
            {item.icon}
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-3 border-t border-mangarr-border">
        <p className="text-mangarr-disabled text-xs">v0.1.0</p>
      </div>
    </aside>
  );
}
