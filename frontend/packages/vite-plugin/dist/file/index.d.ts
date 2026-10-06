interface Item {
    path: string;
    code: string;
}
export declare function createFile(data: Item | Item[]): Promise<void>;
export {};
