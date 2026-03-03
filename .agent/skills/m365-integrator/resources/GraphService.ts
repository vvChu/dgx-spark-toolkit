import { Client } from "@microsoft/microsoft-graph-client";

/**
 * Helper function to create a graph client with a given access token.
 * @param accessToken The valid access token retrieved from MSAL
 */
export const getGraphClient = (accessToken: string) => {
    const client = Client.init({
        authProvider: (done) => {
            done(null, accessToken);
        }
    });

    return client;
};

/**
 * Example function to get user details
 */
export const getUserProfile = async (accessToken: string) => {
    const client = getGraphClient(accessToken);
    const user = await client.api('/me').get();
    return user;
};

/**
 * Example function to list files in root of OneDrive
 */
export const getOneDriveFiles = async (accessToken: string) => {
    const client = getGraphClient(accessToken);
    const response = await client.api('/me/drive/root/children').get();
    return response.value;
}
