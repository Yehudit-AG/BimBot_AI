import React from 'react';
import { useLocation } from 'react-router-dom';

const Header = () => {
  const location = useLocation();
  
  const getPageTitle = () => {
    if (location.pathname === '/') {
      return 'Upload Drawing';
    } else if (location.pathname.includes('/layers')) {
      return 'Layer Management';
    } else if (location.pathname.includes('/jobs')) {
      return 'Job Dashboard';
    }
    return 'BimBot AI Wall';
  };

  const getPageDescription = () => {
    if (location.pathname === '/') {
      return 'Upload your DWG export JSON file to begin processing';
    } else if (location.pathname.includes('/layers')) {
      return 'Select layers for wall detection processing';
    } else if (location.pathname.includes('/jobs')) {
      return 'Monitor job progress and view results';
    }
    return 'AutoCAD DWG export processing with layer-based geometry pipeline';
  };

  return (
    <header className="header">
      <div className="container">
        <h1>BimBot AI Wall</h1>
        <p>{getPageDescription()}</p>
      </div>
    </header>
  );
};

export default Header;