import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BarChart2, Bell, BookOpen, Brain, GraduationCap, Settings, Upload } from 'lucide-react';
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from '@/components/ui/sidebar';
import { Dashboard } from '@/pages/Dashboard';
import { Courses } from '@/pages/Courses';
import { CourseDetail } from '@/pages/CourseDetail';
import { ClassDetail } from '@/pages/ClassDetail';
import { Upload as UploadPage } from '@/pages/Upload';
import { Collections } from '@/pages/Collections';
import { Documents } from '@/pages/Documents';
import { Config } from '@/pages/Config';
import { Learn } from '@/pages/Learn';
import { Stats } from '@/pages/Stats';

const queryClient = new QueryClient();

const NAV_ITEMS = [
  { to: '/', end: true, icon: Bell, label: 'Dashboard' },
  { to: '/courses', end: false, icon: GraduationCap, label: 'Mis Materias' },
  { to: '/learn', end: false, icon: Brain, label: 'Aprender' },
  { to: '/stats', end: false, icon: BarChart2, label: 'Estadísticas' },
  { to: '/upload', end: false, icon: Upload, label: 'Subir Clase' },
  { to: '/config', end: false, icon: Settings, label: 'Configuración' },
];

function AppSidebar() {
  const location = useLocation();

  const isActive = (to: string, end: boolean) => {
    if (end) return location.pathname === to;
    return location.pathname === to || location.pathname.startsWith(to + '/') || location.pathname.startsWith(to + '?');
  };

  return (
    <Sidebar>
      <SidebarHeader>
        <div className="px-2 py-2">
          <h2 className="text-lg font-semibold">EduTranscribe</h2>
          <p className="text-xs text-muted-foreground">Tu asistente de estudio</p>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Navegación</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV_ITEMS.map(({ to, end, icon: Icon, label }) => (
                <SidebarMenuItem key={to}>
                  <SidebarMenuButton asChild isActive={isActive(to, end)}>
                    <NavLink to={to} end={end}>
                      <Icon className="size-4" />
                      <span>{label}</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
              {/* Legacy tools */}
              <SidebarMenuItem>
                <SidebarMenuButton asChild isActive={location.pathname === '/collections'}>
                  <NavLink to="/collections">
                    <BookOpen className="size-4" />
                    <span>Colecciones</span>
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}

function AppContent() {
  const location = useLocation();
  const isWide =
    location.pathname === '/' ||
    location.pathname.startsWith('/courses') ||
    location.pathname.startsWith('/classes') ||
    location.pathname.startsWith('/upload') ||
    location.pathname.startsWith('/stats');

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger />
          <div className="flex-1" />
        </header>
        <main className={`flex-1 p-6 ${isWide ? 'max-w-5xl' : 'max-w-3xl'}`}>
          <Routes>
            {/* Learning tool routes */}
            <Route path="/" element={<Dashboard />} />
            <Route path="/courses" element={<Courses />} />
            <Route path="/courses/:courseId" element={<CourseDetail />} />
            <Route path="/classes/:videoId" element={<ClassDetail />} />
            <Route path="/upload" element={<UploadPage />} />
            <Route path="/learn" element={<Learn />} />
            <Route path="/stats" element={<Stats />} />
            {/* Legacy routes — keep working */}
            <Route path="/collections" element={<Collections />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/config" element={<Config />} />
          </Routes>
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
