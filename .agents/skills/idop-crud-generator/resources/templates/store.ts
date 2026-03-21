import { create } from 'zustand';

interface { { EntityName } } {
    id: string;
    // Add other fields here
}

interface { { EntityName } }State {
    items: { { EntityName } } [];
    isLoading: boolean;
    error: string | null;

    fetchAll: () => Promise<void>;
    createItem: (data: Omit<{{ EntityName }}, 'id' >) => Promise<void>;
deleteItem: (id: string) => Promise<void>;
}

export const use{{ EntityName }}Store = create < {{ EntityName }}State > ((set) => ({
    items: [],
    isLoading: false,
    error: null,

    fetchAll: async () => {
        set({ isLoading: true });
        try {
            const res = await fetch('/api/{{entityName_lowercase}}');
            const data = await res.json();
            set({ items: data, isLoading: false });
        } catch (err) {
            set({ error: 'Failed to fetch', isLoading: false });
        }
    },

    createItem: async (data) => {
        try {
            const res = await fetch('/api/{{entityName_lowercase}}', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const newItem = await res.json();
            set((state) => ({ items: [...state.items, newItem] }));
        } catch (err) {
            console.error(err);
        }
    },

    deleteItem: async (id) => {
        try {
            await fetch(\`/api/{{entityName_lowercase}}/\${id}\`, { method: 'DELETE' });
            set((state) => ({ items: state.items.filter(i => i.id !== id) }));
        } catch (err) {
            console.error(err);
        }
    }
}));
