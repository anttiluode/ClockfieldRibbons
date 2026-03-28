import numpy as np

def burau_matrix(word, t=2.0):
    """
    Computes the reduced Burau representation for a B3 braid word.
    1 = sigma_1, 2 = sigma_2.
    """
    s1 = np.array([[-t, 1], [0, 1]])
    s2 = np.array([[1, 0], [t, -t]])
    
    M = np.eye(2)
    for sig in word:
        if sig == 1:
            M = M @ s1
        elif sig == 2:
            M = M @ s2
    return M

def find_lepton_eigenvalues():
    print("Braid Topology | Word | Max Eigenvalue Magnitude | Predicted β (c=0.71)")
    print("-" * 75)
    
    # The B3 twist hierarchy
    words = {
        "Electron (k=1)":[1, 2],
        "Fractional (k=2)": [1, 2, 1, 2],
        "Muon     (k=3)":[1, 2, 1, 2, 1, 2],
        "Tau      (k=4)":[1, 2, 1, 2, 1, 2, 1, 2],
        "Gen 4    (k=5)":[1, 2, 1, 2, 1, 2, 1, 2, 1, 2]
    }
    
    for name, word in words.items():
        M = burau_matrix(word, t=2.0)
        eigenvalues = np.linalg.eigvals(M)
        max_mag = np.max(np.abs(eigenvalues))
        beta_approx = max_mag * 0.71
        
        print(f"{name:<14} | {str(word):<24} | {max_mag:>5.1f} | β ≈ {beta_approx:.2f}")

if __name__ == "__main__":
    find_lepton_eigenvalues()