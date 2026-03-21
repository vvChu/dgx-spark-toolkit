// Template for {{EntityName}} Controller

import * as service from './service.js';

export const getAll = async (req, res) => {
    try {
        const items = await service.findAll();
        res.json(items);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
};

export const create = async (req, res) => {
    try {
        const newItem = await service.create(req.body);
        res.status(201).json(newItem);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
};

export const update = async (req, res) => {
    try {
        const { id } = req.params;
        const updatedItem = await service.update(id, req.body);
        if (!updatedItem) return res.status(404).json({ message: 'Not found' });
        res.json(updatedItem);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
};

export const remove = async (req, res) => {
    try {
        const { id } = req.params;
        await service.deleteItem(id);
        res.status(204).send();
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
};
