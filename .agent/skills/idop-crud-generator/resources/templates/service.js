// Template for {{EntityName}} Service
import { v4 as uuidv4 } from 'uuid';

// Mock Database
let db = []; // Replace this with real DB calls later

export const findAll = async () => {
    return db;
};

export const create = async (data) => {
    const newItem = { id: uuidv4(), ...data };
    db.push(newItem);
    return newItem;
};

export const update = async (id, data) => {
    const index = db.findIndex(item => item.id === id);
    if (index === -1) return null;

    db[index] = { ...db[index], ...data };
    return db[index];
};

export const deleteItem = async (id) => {
    db = db.filter(item => item.id !== id);
    return true;
};
