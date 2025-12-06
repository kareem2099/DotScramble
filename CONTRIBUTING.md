# Contributing

We welcome contributions to Advanced Image Privacy Studio Pro! This document provides guidelines for contributing to the project.

## How to Contribute

### Reporting Issues
- Use the GitHub issue tracker to report bugs
- Describe the issue clearly with steps to reproduce
- Include your system information and Python version
- Attach sample images if relevant (be mindful of privacy)

### Suggesting Features
- Open a GitHub issue with the "enhancement" label
- Clearly describe the proposed feature
- Explain how it would benefit users
- Consider implementation feasibility

### Code Contributions

#### Development Setup
1. Fork the repository
2. Clone your fork: `git clone https://github.com/yourusername/DotScramble.git`
3. Create a virtual environment: `python -m venv venv`
4. Activate it: `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
5. Install dependencies: `pip install -r requirements.txt`
6. Run the application: `python main.py`

#### Making Changes
1. Create a feature branch: `git checkout -b feature/your-feature-name`
2. Make your changes following the code style guidelines
3. Test your changes thoroughly
4. Update documentation if needed
5. Commit with clear messages: `git commit -m "Add: brief description of changes"`

#### Pull Request Process
1. Ensure your branch is up-to-date with main
2. Push your changes: `git push origin feature/your-feature-name`
3. Create a Pull Request on GitHub
4. Describe your changes and reference any related issues
5. Wait for review and address any feedback

### Code Style Guidelines
- Follow PEP 8 Python style guide
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Comment complex logic
- Keep functions focused on single responsibilities

### Areas for Contribution
- Additional detection algorithms
- New effect types
- Video processing support
- GPU acceleration
- Cloud processing integration
- Mobile app version
- Performance optimizations
- Documentation improvements
- Test coverage

### Testing
- Test on different image types and sizes
- Verify effects work correctly with different parameters
- Check batch processing functionality
- Test GUI responsiveness
- Validate preset loading/saving

## Code of Conduct
- Be respectful and constructive in all interactions
- Focus on improving the project
- Help newcomers learn and contribute
- Report any unacceptable behavior

## License
By contributing, you agree that your contributions will be licensed under the same MIT License that covers the project.

Thank you for contributing to Advanced Image Privacy Studio Pro!
